import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import (Employee, SalaryComponent, SalaryStructure,
                         PayrollEntry, PayrollItem, Account, db)
from app.services.payroll import PayrollService
from app.services.audit import AuditService
from app.decorators import accountant_or_admin_required

payroll_bp = Blueprint('payroll', __name__, url_prefix='/payroll')


# ── Employees ──

@payroll_bp.route('/employees', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def employees():
    if request.method == 'POST':
        try:
            PayrollService.create_employee(
                employee_code=request.form['employee_code'],
                name=request.form['name'],
                department=request.form.get('department'),
                designation=request.form.get('designation'),
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                date_of_joining=request.form.get('date_of_joining'),
                bank_account=request.form.get('bank_account'),
                salary_structure_id=request.form.get('salary_structure_id') or None
            )
            flash('Employee created successfully.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('payroll.employees'))

    all_employees = Employee.query.order_by(Employee.name).all()
    structures = SalaryStructure.query.filter_by(is_active=True).all()
    return render_template('payroll/employees.html', employees=all_employees,
                           structures=structures)


@payroll_bp.route('/employees/<int:id>/edit', methods=['POST'])
@login_required
@accountant_or_admin_required
def edit_employee(id):
    emp = Employee.query.get_or_404(id)
    emp.name = request.form.get('name', emp.name).strip()
    emp.department = request.form.get('department', '').strip()
    emp.designation = request.form.get('designation', '').strip()
    emp.email = request.form.get('email', '').strip()
    emp.phone = request.form.get('phone', '').strip()
    emp.bank_account = request.form.get('bank_account', '').strip()
    ss_id = request.form.get('salary_structure_id')
    emp.salary_structure_id = int(ss_id) if ss_id else None
    db.session.commit()
    flash(f'Employee {emp.name} updated.', 'success')
    return redirect(url_for('payroll.employees'))


# ── Salary Components ──

@payroll_bp.route('/components', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def components():
    if request.method == 'POST':
        try:
            PayrollService.create_salary_component(
                name=request.form['name'],
                component_type=request.form['component_type'],
                is_statutory='is_statutory' in request.form,
                account_id=request.form.get('account_id') or None
            )
            flash('Salary component created.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('payroll.components'))

    all_components = SalaryComponent.query.order_by(SalaryComponent.name).all()
    accounts = Account.query.order_by(Account.code).all()
    return render_template('payroll/components.html', components=all_components,
                           accounts=accounts)


# ── Salary Structures ──

@payroll_bp.route('/salary-structures', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def salary_structures():
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form.get('description', '')
            comp_ids = request.form.getlist('component_id[]')
            amounts = request.form.getlist('amount[]')
            percentages = request.form.getlist('percentage[]')
            base_ids = request.form.getlist('base_component_id[]')

            details = []
            for i in range(len(comp_ids)):
                if comp_ids[i]:
                    details.append({
                        'component_id': comp_ids[i],
                        'amount': amounts[i] if amounts[i] else 0,
                        'percentage': percentages[i] if percentages[i] else 0,
                        'base_component_id': base_ids[i] if base_ids and base_ids[i] else None
                    })

            PayrollService.create_salary_structure(name, details, description)
            flash(f'Salary structure "{name}" created.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('payroll.salary_structures'))

    structures = SalaryStructure.query.order_by(SalaryStructure.name).all()
    all_components = SalaryComponent.query.order_by(SalaryComponent.name).all()
    return render_template('payroll/salary_structures.html',
                           structures=structures, components=all_components)


# ── Payroll Processing ──

@payroll_bp.route('/process', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def process():
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'run':
                period = request.form['period']
                entry = PayrollService.process_payroll(period)
                flash(f'Payroll for {period} processed. Entry #{entry.id} created as Draft.', 'success')
            elif action == 'post':
                entry_id = request.form['payroll_entry_id']
                PayrollService.post_payroll(int(entry_id))
                flash('Payroll posted to General Ledger.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('payroll.process'))

    entries = PayrollEntry.query.order_by(PayrollEntry.created_at.desc()).all()
    return render_template('payroll/process.html', entries=entries)


@payroll_bp.route('/payslip/<int:id>')
@login_required
def payslip(id):
    pi = PayrollItem.query.get_or_404(id)
    components = json.loads(pi.components_json) if pi.components_json else []
    return render_template('payroll/payslip.html', item=pi, components=components)
