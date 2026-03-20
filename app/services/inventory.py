from app.extensions import db
from app.models import (Product, Warehouse, StockEntry, StockEntryItem,
                         StockLedgerEntry, Account)
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from datetime import datetime
from sqlalchemy import func


class InventoryService:
    # ── Product CRUD ──

    @staticmethod
    def create_product(sku, name, unit='Nos', purchase_price=0, selling_price=0,
                       valuation_method='AVG', description=None,
                       inventory_account_id=None, expense_account_id=None,
                       revenue_account_id=None):
        product = Product(
            sku=sku, name=name, unit=unit,
            purchase_price=purchase_price, selling_price=selling_price,
            valuation_method=valuation_method, description=description,
            inventory_account_id=inventory_account_id,
            expense_account_id=expense_account_id,
            revenue_account_id=revenue_account_id
        )
        db.session.add(product)
        db.session.commit()
        AuditService.log(action='CREATE', model='Product', model_id=product.id,
                         details=f"Created product {sku} — {name}")
        return product

    # ── Warehouse CRUD ──

    @staticmethod
    def create_warehouse(name, location=None):
        wh = Warehouse(name=name, location=location)
        db.session.add(wh)
        db.session.commit()
        return wh

    # ── Stock Balance helpers ──

    @staticmethod
    def get_stock_balance(product_id, warehouse_id=None):
        """Returns current qty and value for a product (optionally per warehouse)."""
        q = db.session.query(
            func.sum(StockLedgerEntry.qty_change).label('qty'),
            func.sum(StockLedgerEntry.qty_change * StockLedgerEntry.valuation_rate).label('value')
        ).filter_by(product_id=product_id)
        if warehouse_id:
            q = q.filter_by(warehouse_id=warehouse_id)
        row = q.first()
        return {
            'qty': float(row.qty or 0),
            'value': float(row.value or 0)
        }

    @staticmethod
    def get_all_stock_balances():
        """Returns stock balance grouped by product + warehouse."""
        rows = db.session.query(
            StockLedgerEntry.product_id,
            StockLedgerEntry.warehouse_id,
            func.sum(StockLedgerEntry.qty_change).label('qty'),
        ).group_by(
            StockLedgerEntry.product_id,
            StockLedgerEntry.warehouse_id
        ).all()

        result = []
        for r in rows:
            product = Product.query.get(r.product_id)
            warehouse = Warehouse.query.get(r.warehouse_id)
            if product and warehouse:
                result.append({
                    'product': product,
                    'warehouse': warehouse,
                    'qty': float(r.qty or 0)
                })
        return result

    # ── Stock Entry Processing ──

    @staticmethod
    def process_stock_entry(entry_type, date, items, source_warehouse_id=None,
                            target_warehouse_id=None, reference=None, notes=None):
        """
        Process a stock entry.
        entry_type: 'Receipt' | 'Issue' | 'Transfer'
        items: list of {'product_id': int, 'quantity': float, 'rate': float}
        """
        if isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d')

        entry = StockEntry(
            entry_type=entry_type, date=date, reference=reference, notes=notes,
            source_warehouse_id=source_warehouse_id,
            target_warehouse_id=target_warehouse_id
        )
        db.session.add(entry)
        db.session.flush()

        total_value = 0
        for item_data in items:
            product = Product.query.get(item_data['product_id'])
            qty = float(item_data['quantity'])
            rate = float(item_data.get('rate', product.purchase_price if product else 0))
            amount = qty * rate

            sei = StockEntryItem(
                stock_entry_id=entry.id,
                product_id=item_data['product_id'],
                quantity=qty, rate=rate, amount=amount
            )
            db.session.add(sei)
            total_value += amount

            # Update Stock Ledger
            if entry_type == 'Receipt':
                InventoryService._update_stock_ledger(
                    product_id=item_data['product_id'],
                    warehouse_id=target_warehouse_id,
                    qty_change=qty, rate=rate,
                    posting_date=date, stock_entry_id=entry.id
                )
            elif entry_type == 'Issue':
                InventoryService._update_stock_ledger(
                    product_id=item_data['product_id'],
                    warehouse_id=source_warehouse_id,
                    qty_change=-qty, rate=rate,
                    posting_date=date, stock_entry_id=entry.id
                )
            elif entry_type == 'Transfer':
                # Out from source
                InventoryService._update_stock_ledger(
                    product_id=item_data['product_id'],
                    warehouse_id=source_warehouse_id,
                    qty_change=-qty, rate=rate,
                    posting_date=date, stock_entry_id=entry.id
                )
                # In to target
                InventoryService._update_stock_ledger(
                    product_id=item_data['product_id'],
                    warehouse_id=target_warehouse_id,
                    qty_change=qty, rate=rate,
                    posting_date=date, stock_entry_id=entry.id
                )

        # Auto-post GL entry for Receipt/Issue
        if entry_type in ('Receipt', 'Issue') and total_value > 0:
            product = Product.query.get(items[0]['product_id'])
            inv_acc = product.inventory_account if product else None
            exp_acc = product.expense_account if product else None

            if inv_acc and exp_acc:
                if entry_type == 'Receipt':
                    je_items = [
                        {'account_id': inv_acc.id, 'debit': total_value, 'credit': 0},
                        {'account_id': exp_acc.id, 'debit': 0, 'credit': total_value},
                    ]
                else:
                    je_items = [
                        {'account_id': exp_acc.id, 'debit': total_value, 'credit': 0},
                        {'account_id': inv_acc.id, 'debit': 0, 'credit': total_value},
                    ]
                try:
                    je = AccountingService.create_journal_entry(
                        date=date,
                        description=f"Stock {entry_type} #{entry.id}",
                        items=je_items,
                        reference=f"SE-{entry.id}"
                    )
                    entry.journal_entry_id = je.id
                except Exception:
                    pass  # GL posting is best-effort

        db.session.commit()
        AuditService.log(action='CREATE', model='StockEntry', model_id=entry.id,
                         details=f"Stock {entry_type} processed")
        return entry

    @staticmethod
    def _update_stock_ledger(product_id, warehouse_id, qty_change, rate,
                             posting_date, stock_entry_id=None):
        """Appends a row to the perpetual stock ledger with running balance."""
        # Current balance
        bal = InventoryService.get_stock_balance(product_id, warehouse_id)
        new_qty = bal['qty'] + qty_change

        # Weighted average valuation
        if qty_change > 0 and new_qty > 0:
            new_value = bal['value'] + (qty_change * rate)
            new_rate = new_value / new_qty
        else:
            new_rate = rate if new_qty == 0 else bal['value'] / bal['qty'] if bal['qty'] else 0
            new_value = new_qty * new_rate

        sle = StockLedgerEntry(
            product_id=product_id,
            warehouse_id=warehouse_id,
            posting_date=posting_date,
            qty_change=qty_change,
            valuation_rate=round(new_rate, 2),
            balance_qty=round(new_qty, 3),
            balance_value=round(new_value, 2),
            stock_entry_id=stock_entry_id
        )
        db.session.add(sle)
