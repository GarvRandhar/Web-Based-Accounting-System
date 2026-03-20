from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Product, Warehouse, StockEntry, StockLedgerEntry, Account, db
from app.services.inventory import InventoryService
from app.services.audit import AuditService

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route('/products', methods=['GET', 'POST'])
@login_required
def products():
    if request.method == 'POST':
        try:
            InventoryService.create_product(
                sku=request.form['sku'],
                name=request.form['name'],
                unit=request.form.get('unit', 'Nos'),
                purchase_price=float(request.form.get('purchase_price', 0)),
                selling_price=float(request.form.get('selling_price', 0)),
                valuation_method=request.form.get('valuation_method', 'AVG'),
                description=request.form.get('description'),
                inventory_account_id=request.form.get('inventory_account_id') or None,
                expense_account_id=request.form.get('expense_account_id') or None,
                revenue_account_id=request.form.get('revenue_account_id') or None,
            )
            flash('Product created successfully.', 'success')
        except Exception as e:
            flash(f'Error creating product: {e}', 'error')
        return redirect(url_for('inventory.products'))

    all_products = Product.query.order_by(Product.name).all()
    asset_accounts = Account.query.filter_by(type='Asset').order_by(Account.code).all()
    expense_accounts = Account.query.filter_by(type='Expense').order_by(Account.code).all()
    revenue_accounts = Account.query.filter_by(type='Revenue').order_by(Account.code).all()

    # Attach stock balance to each product
    for p in all_products:
        bal = InventoryService.get_stock_balance(p.id)
        p._stock_qty = bal['qty']
        p._stock_value = bal['value']

    return render_template('inventory/products.html', products=all_products,
                           asset_accounts=asset_accounts,
                           expense_accounts=expense_accounts,
                           revenue_accounts=revenue_accounts)


@inventory_bp.route('/products/<int:id>/edit', methods=['POST'])
@login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    product.name = request.form.get('name', product.name).strip()
    product.sku = request.form.get('sku', product.sku).strip()
    product.unit = request.form.get('unit', product.unit).strip()
    product.purchase_price = float(request.form.get('purchase_price', product.purchase_price))
    product.selling_price = float(request.form.get('selling_price', product.selling_price))
    db.session.commit()
    flash(f'Product {product.name} updated.', 'success')
    return redirect(url_for('inventory.products'))


@inventory_bp.route('/warehouses', methods=['GET', 'POST'])
@login_required
def warehouses():
    if request.method == 'POST':
        try:
            InventoryService.create_warehouse(
                name=request.form['name'],
                location=request.form.get('location')
            )
            flash('Warehouse created successfully.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('inventory.warehouses'))

    all_warehouses = Warehouse.query.order_by(Warehouse.name).all()
    return render_template('inventory/warehouses.html', warehouses=all_warehouses)


@inventory_bp.route('/stock-entry/new', methods=['GET', 'POST'])
@login_required
def new_stock_entry():
    if request.method == 'POST':
        try:
            entry_type = request.form['entry_type']
            date = request.form['date']
            source_wh = request.form.get('source_warehouse_id') or None
            target_wh = request.form.get('target_warehouse_id') or None

            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            rates = request.form.getlist('rate[]')

            items = []
            for i in range(len(product_ids)):
                if product_ids[i]:
                    items.append({
                        'product_id': int(product_ids[i]),
                        'quantity': float(quantities[i]),
                        'rate': float(rates[i]) if rates[i] else 0,
                    })

            InventoryService.process_stock_entry(
                entry_type=entry_type, date=date, items=items,
                source_warehouse_id=int(source_wh) if source_wh else None,
                target_warehouse_id=int(target_wh) if target_wh else None,
                reference=request.form.get('reference'),
                notes=request.form.get('notes')
            )
            flash(f'Stock {entry_type} processed successfully.', 'success')
            return redirect(url_for('inventory.stock_ledger'))
        except Exception as e:
            flash(f'Error: {e}', 'error')

    all_products = Product.query.filter_by(is_active=True).all()
    all_warehouses = Warehouse.query.filter_by(is_active=True).all()
    return render_template('inventory/stock_entry.html',
                           products=all_products, warehouses=all_warehouses)


@inventory_bp.route('/stock-ledger')
@login_required
def stock_ledger():
    product_id = request.args.get('product_id', type=int)
    warehouse_id = request.args.get('warehouse_id', type=int)

    q = StockLedgerEntry.query
    if product_id:
        q = q.filter_by(product_id=product_id)
    if warehouse_id:
        q = q.filter_by(warehouse_id=warehouse_id)

    entries = q.order_by(StockLedgerEntry.posting_date.desc()).limit(200).all()
    products = Product.query.filter_by(is_active=True).all()
    whs = Warehouse.query.filter_by(is_active=True).all()

    return render_template('inventory/stock_ledger.html', entries=entries,
                           products=products, warehouses=whs,
                           selected_product=product_id, selected_warehouse=warehouse_id)
