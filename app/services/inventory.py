from app.extensions import db
from app.models import (Product, Warehouse, StockEntry, StockEntryItem,
                         StockLedgerEntry, Account)
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from datetime import datetime, timezone
from sqlalchemy import func


def _now():
    return datetime.now(timezone.utc)


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

        product_ids = {r.product_id for r in rows}
        warehouse_ids = {r.warehouse_id for r in rows}
        products_by_id = {
            p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()
        } if product_ids else {}
        warehouses_by_id = {
            w.id: w for w in Warehouse.query.filter(Warehouse.id.in_(warehouse_ids)).all()
        } if warehouse_ids else {}

        result = []
        for r in rows:
            product = products_by_id.get(r.product_id)
            warehouse = warehouses_by_id.get(r.warehouse_id)
            if product and warehouse:
                result.append({
                    'product': product,
                    'warehouse': warehouse,
                    'qty': float(r.qty or 0)
                })
        return result

    @staticmethod
    def get_stock_balances_for_products(product_ids):
        """Returns {product_id: {'qty': float, 'value': float}} for all requested products."""
        if not product_ids:
            return {}
        rows = db.session.query(
            StockLedgerEntry.product_id,
            func.sum(StockLedgerEntry.qty_change).label('qty'),
            func.sum(StockLedgerEntry.qty_change * StockLedgerEntry.valuation_rate).label('value')
        ).filter(
            StockLedgerEntry.product_id.in_(set(product_ids))
        ).group_by(
            StockLedgerEntry.product_id
        ).all()
        balances = {
            r.product_id: {'qty': float(r.qty or 0), 'value': float(r.value or 0)}
            for r in rows
        }
        for product_id in product_ids:
            balances.setdefault(product_id, {'qty': 0.0, 'value': 0.0})
        return balances

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

        valid_types = {'Receipt', 'Issue', 'Transfer'}
        if entry_type not in valid_types:
            raise ValueError(f"Invalid stock entry type: {entry_type}.")
        if not isinstance(items, list) or not items:
            raise ValueError("Stock entry must contain at least one item.")
        if entry_type == 'Transfer' and source_warehouse_id == target_warehouse_id:
            raise ValueError("Source and target warehouses cannot be the same for a transfer.")
        if entry_type in ('Issue', 'Transfer') and not source_warehouse_id:
            raise ValueError("Source warehouse is required for issue/transfer entries.")
        if entry_type in ('Receipt', 'Transfer') and not target_warehouse_id:
            raise ValueError("Target warehouse is required for receipt/transfer entries.")

        entry = StockEntry(
            entry_type=entry_type, date=date, reference=reference, notes=notes,
            source_warehouse_id=source_warehouse_id,
            target_warehouse_id=target_warehouse_id
        )
        db.session.add(entry)
        db.session.flush()

        total_value = 0
        line_items = []
        for idx, item_data in enumerate(items, start=1):
            if not isinstance(item_data, dict):
                raise ValueError(f"Line {idx}: item must be an object.")
            if 'product_id' not in item_data:
                raise ValueError(f"Line {idx}: product_id is required.")
            if 'quantity' not in item_data:
                raise ValueError(f"Line {idx}: quantity is required.")
            line_items.append(item_data)

        for item_data in line_items:
            # Pessimistic locking to prevent concurrent inventory race conditions
            product = db.session.query(Product).filter_by(id=item_data['product_id']).with_for_update().first()
            if not product:
                raise ValueError(f"Product ID {item_data['product_id']} not found.")
            qty = float(item_data['quantity'])
            if qty <= 0:
                raise ValueError(f"Quantity for product '{product.name}' must be greater than zero.")

            # ── Negative stock guard ───────────────────────────────────
            # For Issue and Transfer, check available stock BEFORE creating any SLE.
            if entry_type in ('Issue', 'Transfer'):
                bal = InventoryService.get_stock_balance(product.id, source_warehouse_id)
                available = float(bal['qty'])
                if available < qty:
                    wh = db.session.get(Warehouse, source_warehouse_id)
                    wh_name = wh.name if wh else f"#{source_warehouse_id}"
                    raise ValueError(
                        f"Insufficient stock for '{product.name}' in warehouse '{wh_name}': "
                        f"available {available:.3f}, requested {qty:.3f}."
                    )
                if product.valuation_method == 'FIFO':
                    # Dynamic layer exhaustion algorithm
                    # 1. Get all chronological receipts arrays
                    receipts = StockLedgerEntry.query.filter_by(
                        product_id=product.id, warehouse_id=source_warehouse_id
                    ).filter(StockLedgerEntry.qty_change > 0).order_by(
                        StockLedgerEntry.posting_date.asc(), StockLedgerEntry.id.asc()
                    ).all()
                    
                    # 2. Get the global sum of historical issues
                    issues = StockLedgerEntry.query.filter_by(
                        product_id=product.id, warehouse_id=source_warehouse_id
                    ).filter(StockLedgerEntry.qty_change < 0).all()
                    issued_so_far = sum(abs(float(i.qty_change)) for i in issues)
                    
                    # 3. Simulate sequential consumption to find surviving batches
                    surviving_layers = []
                    for r in receipts:
                        r_qty = float(r.qty_change)
                        if issued_so_far >= r_qty:
                            issued_so_far -= r_qty
                        else:
                            surviving = r_qty - issued_so_far
                            issued_so_far = 0
                            surviving_layers.append({'rate': float(r.valuation_rate), 'qty': surviving})
                            
                    # 4. Extract total cost from the lowest surviving indexes
                    fulfilled_qty = 0
                    total_cost = 0
                    for layer in surviving_layers:
                        take = min(qty - fulfilled_qty, layer['qty'])
                        total_cost += take * layer['rate']
                        fulfilled_qty += take
                        if fulfilled_qty >= qty:
                            break
                            
                    rate = (total_cost / qty) if qty > 0 else 0
                else:    
                    rate = (bal['value'] / available) if available > 0 else 0
            else:
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
            debit_map = {}
            credit_map = {}
            for sei in entry.items:
                product = db.session.get(Product, sei.product_id)
                if not product or not product.inventory_account_id or not product.expense_account_id:
                    continue
                amount = float(sei.amount or 0)
                if amount <= 0:
                    continue
                if entry_type == 'Receipt':
                    debit_map[product.inventory_account_id] = debit_map.get(product.inventory_account_id, 0) + amount
                    credit_map[product.expense_account_id] = credit_map.get(product.expense_account_id, 0) + amount
                else:
                    debit_map[product.expense_account_id] = debit_map.get(product.expense_account_id, 0) + amount
                    credit_map[product.inventory_account_id] = credit_map.get(product.inventory_account_id, 0) + amount

            je_items = []
            for account_id, debit in debit_map.items():
                je_items.append({'account_id': account_id, 'debit': round(debit, 2), 'credit': 0})
            for account_id, credit in credit_map.items():
                je_items.append({'account_id': account_id, 'debit': 0, 'credit': round(credit, 2)})

            if je_items:
                je = AccountingService.create_journal_entry(
                    date=date,
                    description=f"Stock {entry_type} #{entry.id}",
                    items=je_items,
                    reference=f"SE-{entry.id}"
                )
                entry.journal_entry_id = je.id

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
