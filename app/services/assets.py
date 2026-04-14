from app.extensions import db
from app.models import FixedAsset, DepreciationSchedule, Account
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta


class AssetService:
    @staticmethod
    def create_asset(asset_code, name, purchase_date, purchase_price,
                     useful_life_years, depreciation_method='SLM',
                     salvage_value=0, description=None,
                     asset_account_id=None, depreciation_account_id=None,
                     accumulated_dep_account_id=None):
        if isinstance(purchase_date, str):
            purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()

        asset = FixedAsset(
            asset_code=asset_code, name=name, description=description,
            purchase_date=purchase_date,
            purchase_price=purchase_price, salvage_value=salvage_value,
            useful_life_years=useful_life_years,
            depreciation_method=depreciation_method,
            asset_account_id=asset_account_id,
            depreciation_account_id=depreciation_account_id,
            accumulated_dep_account_id=accumulated_dep_account_id
        )
        db.session.add(asset)
        db.session.commit()

        # Auto-generate depreciation schedule
        AssetService.generate_depreciation_schedule(asset)

        AuditService.log(action='CREATE', model='FixedAsset', model_id=asset.id,
                         details=f"Created asset: {asset_code} — {name}")
        return asset

    @staticmethod
    def generate_depreciation_schedule(asset):
        """
        Generates a monthly depreciation schedule.
        SLM: equal monthly amounts over useful life.
        WDV: declining balance (rate = 1 - (salvage/cost)^(1/life)), applied yearly then /12.
        """
        # Clear any existing un-posted schedule
        DepreciationSchedule.query.filter_by(asset_id=asset.id)\
            .filter(DepreciationSchedule.journal_entry_id.is_(None)).delete()
        db.session.flush()

        total_months = asset.useful_life_years * 12
        depreciable = float(asset.purchase_price) - float(asset.salvage_value)

        if asset.depreciation_method == 'SLM':
            monthly_dep = round(depreciable / total_months, 2) if total_months else 0
            accumulated = float(asset.total_depreciated)

            for i in range(1, total_months + 1):
                schedule_date = asset.purchase_date + relativedelta(months=i)
                # Last month adjustment for rounding
                if i == total_months:
                    monthly_dep = depreciable - accumulated
                accumulated += monthly_dep

                ds = DepreciationSchedule(
                    asset_id=asset.id,
                    schedule_date=schedule_date,
                    depreciation_amount=round(monthly_dep, 2),
                    accumulated_depreciation=round(accumulated, 2)
                )
                db.session.add(ds)

        elif asset.depreciation_method == 'WDV':
            # Written Down Value (Declining Balance)
            purchase = float(asset.purchase_price)
            salvage = float(asset.salvage_value)
            if purchase <= 0 or salvage < 0:
                return

            # Yearly rate: r = 1 - (salvage/cost)^(1/n)
            if salvage > 0:
                rate = 1 - (salvage / purchase) ** (1 / asset.useful_life_years)
            else:
                rate = 2 / asset.useful_life_years  # Double declining if salvage=0

            wdv = purchase
            accumulated = 0

            for year in range(asset.useful_life_years):
                yearly_dep = round(wdv * rate, 2)
                monthly_dep = round(yearly_dep / 12, 2)

                for month in range(1, 13):
                    idx = year * 12 + month
                    schedule_date = asset.purchase_date + relativedelta(months=idx)

                    # Last month of last year: adjust
                    if year == asset.useful_life_years - 1 and month == 12:
                        monthly_dep = round(depreciable - accumulated, 2)

                    accumulated += monthly_dep
                    ds = DepreciationSchedule(
                        asset_id=asset.id,
                        schedule_date=schedule_date,
                        depreciation_amount=round(monthly_dep, 2),
                        accumulated_depreciation=round(accumulated, 2)
                    )
                    db.session.add(ds)

                wdv -= yearly_dep

        db.session.commit()

    @staticmethod
    def post_depreciation(schedule_id):
        """Posts a single depreciation schedule entry to the GL."""
        ds = db.session.get(DepreciationSchedule, schedule_id)
        if not ds:
            raise ValueError("Depreciation schedule not found.")
        if ds.journal_entry_id:
            raise ValueError("Already posted.")

        asset = ds.asset
        dep_acc = asset.depreciation_account_id
        acc_dep_acc = asset.accumulated_dep_account_id

        if not dep_acc or not acc_dep_acc:
            raise ValueError("Asset GL accounts not configured (Depreciation Expense / Accumulated Depreciation).")

        amount = float(ds.depreciation_amount)
        je = AccountingService.create_journal_entry(
            date=ds.schedule_date,
            description=f"Depreciation — {asset.name} ({ds.schedule_date})",
            items=[
                {'account_id': dep_acc, 'debit': amount, 'credit': 0},
                {'account_id': acc_dep_acc, 'debit': 0, 'credit': amount}
            ],
            reference=f"DEP-{asset.asset_code}-{ds.id}"
        )
        ds.journal_entry_id = je.id
        db.session.commit()
        return ds

    @staticmethod
    def dispose_asset(asset_id, disposed_date=None, disposed_amount=0):
        """
        Disposes/sells an asset, recording any gain or loss in the GL.

        Journal Entry on disposal:
          Dr  Accumulated Depreciation   (total posted depreciation)
          Dr  Bank / Cash               (sale proceeds, if any)
          Cr  Fixed Asset Account        (original purchase price)
          Dr/Cr Gain or Loss on Disposal (balancing amount)
        """
        asset = db.session.get(FixedAsset, asset_id)
        if not asset:
            raise ValueError("Asset not found.")
        if asset.status != 'Active':
            raise ValueError("Asset is not active.")

        if isinstance(disposed_date, str):
            disposed_date = datetime.strptime(disposed_date, '%Y-%m-%d').date()
        disposed_date = disposed_date or datetime.now(timezone.utc).date()
        disposed_amount = float(disposed_amount)

        # ── Validate required GL accounts ──────────────────────────────
        if not asset.asset_account_id:
            raise ValueError("Asset GL account not configured. Cannot post disposal entry.")
        if not asset.accumulated_dep_account_id:
            raise ValueError("Accumulated Depreciation account not configured. Cannot post disposal entry.")

        total_posted_dep = asset.total_depreciated           # sum of posted depreciation only
        purchase_price   = float(asset.purchase_price)
        book_value       = purchase_price - total_posted_dep  # Net Book Value
        gain_loss        = disposed_amount - book_value        # +ve = gain, -ve = loss

        # ── Build double-entry journal ──────────────────────────────────
        je_items = []

        # 1. Remove Accumulated Depreciation (Dr)
        if total_posted_dep > 0:
            je_items.append({
                'account_id': asset.accumulated_dep_account_id,
                'debit': round(total_posted_dep, 2),
                'credit': 0
            })

        # 2. Remove Asset at Cost (Cr)
        je_items.append({
            'account_id': asset.asset_account_id,
            'debit': 0,
            'credit': round(purchase_price, 2)
        })

        # 3. Record cash/bank proceeds (Dr)
        if disposed_amount > 0:
            bank_account = Account.query.filter_by(code='1020').first()
            if not bank_account:
                # Fallback to Cash
                bank_account = Account.query.filter_by(code='1010').first()
            if not bank_account:
                raise ValueError("No Bank (1020) or Cash (1010) account found to record disposal proceeds.")
            je_items.append({
                'account_id': bank_account.id,
                'debit': round(disposed_amount, 2),
                'credit': 0
            })

        # 4. Recognise Gain or Loss (balancing entry)
        #    Gain → Credit a Revenue / Other Income account
        #    Loss → Debit an Expense account
        #    We use the Depreciation Expense account as a proxy for gain/loss unless
        #    a dedicated account exists.
        if abs(gain_loss) > 0.01:
            gl_account = (
                asset.depreciation_account_id or
                (Account.query.filter_by(code='5010').first() or Account.query.filter_by(type='Expense').first()).id
            )
            if gain_loss > 0:
                # Gain on disposal → Credit
                je_items.append({'account_id': gl_account, 'debit': 0, 'credit': round(gain_loss, 2)})
            else:
                # Loss on disposal → Debit
                je_items.append({'account_id': gl_account, 'debit': round(abs(gain_loss), 2), 'credit': 0})

        AccountingService.create_journal_entry(
            date=disposed_date,
            description=f"Asset Disposal: {asset.name} ({asset.asset_code})",
            items=je_items,
            reference=f"DISP-{asset.asset_code}"
        )

        # ── Update asset record ─────────────────────────────────────────
        asset.status = 'Sold' if disposed_amount > 0 else 'Disposed'
        asset.disposed_date = disposed_date
        asset.disposed_amount = disposed_amount
        db.session.commit()

        AuditService.log(action='UPDATE', model='FixedAsset', model_id=asset.id,
                         details=f"Asset disposed: {asset.name}, proceeds: {disposed_amount}, gain/loss: {gain_loss:.2f}")
        return asset
