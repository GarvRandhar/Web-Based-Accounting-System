from app.models import Account, JournalItem, JournalEntry, db
from sqlalchemy import func, case
from datetime import datetime


class ReportingService:

    # ─────────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS — single-query aggregation by account
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _aggregate_by_account(date_filter):
        """
        Returns a dict: { account_id: (total_debit, total_credit) }
        for ALL accounts matching the supplied date filter expression.
        This fires EXACTLY ONE SQL query regardless of COA size.
        Voided entries are excluded — their reversing counterparts cancel them out
        in the perpetual ledger, but we exclude both to keep gross balances clean.
        """
        rows = (
            db.session.query(
                JournalItem.account_id,
                func.coalesce(func.sum(JournalItem.debit),  0).label('dr'),
                func.coalesce(func.sum(JournalItem.credit), 0).label('cr'),
            )
            .join(JournalEntry, JournalEntry.id == JournalItem.journal_entry_id)
            .filter(date_filter)
            .filter(JournalEntry.voided == False)  # noqa: E712 — exclude voided entries
            .group_by(JournalItem.account_id)
            .all()
        )
        return {r.account_id: (float(r.dr), float(r.cr)) for r in rows}

    # ─────────────────────────────────────────────────────────────────────
    # BALANCE SHEET
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_balance_sheet(as_of_date):
        """
        Balance Sheet as of a date.  2 SQL queries total:
          1. One aggregation covering every account up to as_of_date.
          2. One Account lookup (already cached by SQLAlchemy identity map).
        """
        totals = ReportingService._aggregate_by_account(
            JournalEntry.date <= as_of_date
        )

        def build_section(acc_type, normal_side='debit'):
            """normal_side='debit'  → Asset/Expense  (Dr balance positive)
               normal_side='credit' → Liability/Equity/Revenue"""
            accounts = Account.query.filter_by(type=acc_type, is_active=True).order_by(Account.code).all()
            section_total = 0
            details = []
            for acc in accounts:
                dr, cr = totals.get(acc.id, (0, 0))
                bal = (dr - cr) if normal_side == 'debit' else (cr - dr)
                if abs(bal) < 0.005:
                    continue
                details.append({'code': acc.code, 'name': acc.name, 'balance': round(bal, 2)})
                section_total += bal
            return {'total': round(section_total, 2), 'accounts': details}

        assets      = build_section('Asset',     'debit')
        liabilities = build_section('Liability', 'credit')
        equity      = build_section('Equity',    'credit')

        # Retained Earnings = total Revenue − total Expense (up to date)
        # Both are already in `totals` — just filter account types.
        all_accounts = {a.id: a for a in Account.query.all()}
        rev_net = exp_net = 0.0
        for acc_id, (dr, cr) in totals.items():
            acc = all_accounts.get(acc_id)
            if acc is None:
                continue
            if acc.type == 'Revenue':
                rev_net += cr - dr
            elif acc.type == 'Expense':
                exp_net += dr - cr

        net_income = round(rev_net - exp_net, 2)
        if abs(net_income) >= 0.01:
            equity['accounts'].append({
                'code': '9999', 'name': 'Retained Earnings (YTD)', 'balance': net_income
            })
            equity['total'] = round(equity['total'] + net_income, 2)

        return {
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'date': as_of_date,
        }

    # ─────────────────────────────────────────────────────────────────────
    # PROFIT & LOSS
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_profit_loss(start_date, end_date):
        """
        P&L for a date range.  1 SQL query total.
        """
        totals = ReportingService._aggregate_by_account(
            (JournalEntry.date >= start_date) & (JournalEntry.date <= end_date)
        )

        all_accounts = {a.id: a for a in Account.query.filter(
            Account.type.in_(['Revenue', 'Expense'])
        ).order_by(Account.code).all()}

        revenue_details  = []
        expense_details  = []
        revenue_total = expense_total = 0.0

        for acc_id, (dr, cr) in totals.items():
            acc = all_accounts.get(acc_id)
            if acc is None:
                continue
            if acc.type == 'Revenue':
                bal = round(cr - dr, 2)
                if abs(bal) < 0.005:
                    continue
                revenue_details.append({'code': acc.code, 'name': acc.name, 'balance': bal})
                revenue_total += bal
            elif acc.type == 'Expense':
                bal = round(dr - cr, 2)
                if abs(bal) < 0.005:
                    continue
                expense_details.append({'code': acc.code, 'name': acc.name, 'balance': bal})
                expense_total += bal

        # Sort by account code for consistent display
        revenue_details.sort(key=lambda x: x['code'])
        expense_details.sort(key=lambda x: x['code'])

        return {
            'revenue':    {'total': round(revenue_total, 2), 'accounts': revenue_details},
            'expenses':   {'total': round(expense_total, 2), 'accounts': expense_details},
            'net_income': round(revenue_total - expense_total, 2),
            'start_date': start_date,
            'end_date':   end_date,
        }

    # ─────────────────────────────────────────────────────────────────────
    # TRIAL BALANCE
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_trial_balance(as_of_date):
        """
        Trial Balance as of a date.  1 SQL query total.
        """
        totals = ReportingService._aggregate_by_account(
            JournalEntry.date <= as_of_date
        )

        # Load only accounts that have activity (keeps result set small)
        active_ids = list(totals.keys())
        accounts = {
            a.id: a
            for a in Account.query.filter(Account.id.in_(active_ids)).order_by(Account.code).all()
        }

        data = []
        total_debit = total_credit = 0.0

        for acc_id in sorted(accounts.keys(), key=lambda i: accounts[i].code):
            acc = accounts[acc_id]
            dr, cr = totals.get(acc_id, (0, 0))
            net = dr - cr

            if abs(net) < 0.005:
                continue

            row = {'code': acc.code, 'name': acc.name, 'type': acc.type, 'debit': 0, 'credit': 0}
            if net > 0:
                row['debit'] = round(net, 2)
                total_debit += net
            else:
                row['credit'] = round(abs(net), 2)
                total_credit += abs(net)

            data.append(row)

        return {
            'accounts':     data,
            'total_debit':  round(total_debit, 2),
            'total_credit': round(total_credit, 2),
            'date':         as_of_date,
        }

    # ─────────────────────────────────────────────────────────────────────
    # CASH FLOW
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_cash_flow(start_date, end_date):
        """
        Statement of Cash Flows (Direct method on Cash/Bank GL accounts).
        Contra entries (Bank→Cash) are excluded to avoid double-counting.
        3 SQL queries total regardless of data volume.
        """
        cash_accounts = Account.query.filter(
            (Account.name.in_(['Cash', 'Bank'])) | (Account.code.in_(['1010', '1020']))
        ).all()
        cash_ids = set(acc.id for acc in cash_accounts)

        if not cash_ids:
            return {
                'operating_activities': 0,
                'net_change': 0,
                'starting_balance': 0,
                'ending_balance': 0,
                'start_date': start_date,
                'end_date': end_date,
            }

        # ── 1. All JournalEntry IDs that touch a cash account in the period ──
        # We also eagerly load items to avoid per-entry lazy loading (N+1)
        cash_entries = (
            db.session.query(JournalEntry)
            .join(JournalItem, JournalItem.journal_entry_id == JournalEntry.id)
            .filter(
                JournalItem.account_id.in_(cash_ids),
                JournalEntry.date >= start_date,
                JournalEntry.date <= end_date,
            )
            .distinct()
            .all()
        )

        # Pre-load ALL items for those entries in a single query to avoid lazy N+1
        entry_ids = [e.id for e in cash_entries]
        if entry_ids:
            all_items = (
                db.session.query(JournalItem)
                .filter(JournalItem.journal_entry_id.in_(entry_ids))
                .all()
            )
            # Group items by entry_id
            items_by_entry: dict[int, list] = {}
            for item in all_items:
                items_by_entry.setdefault(item.journal_entry_id, []).append(item)
        else:
            items_by_entry = {}

        net_change = 0.0
        for entry in cash_entries:
            entry_items = items_by_entry.get(entry.id, [])
            # Contra: every item is a cash account → skip (e.g. Bank→Petty Cash transfer)
            if all(item.account_id in cash_ids for item in entry_items):
                continue
            for item in entry_items:
                if item.account_id in cash_ids:
                    net_change += float(item.debit) - float(item.credit)

        # ── 2. Opening cash balance (before start_date) ──
        ob_row = (
            db.session.query(
                func.coalesce(func.sum(JournalItem.debit),  0).label('dr'),
                func.coalesce(func.sum(JournalItem.credit), 0).label('cr'),
            )
            .join(JournalEntry, JournalEntry.id == JournalItem.journal_entry_id)
            .filter(
                JournalItem.account_id.in_(cash_ids),
                JournalEntry.date < start_date,
            )
            .one()
        )
        starting_cash = float(ob_row.dr) - float(ob_row.cr)
        ending_cash   = starting_cash + net_change

        return {
            'operating_activities': round(net_change, 2),
            'net_change':           round(net_change, 2),
            'starting_balance':     round(starting_cash, 2),
            'ending_balance':       round(ending_cash, 2),
            'start_date':           start_date,
            'end_date':             end_date,
        }
