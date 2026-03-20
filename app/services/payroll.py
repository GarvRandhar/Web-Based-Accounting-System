import json
from app.extensions import db
from app.models import (Employee, SalaryComponent, SalaryStructure,
                         SalaryStructureDetail, PayrollEntry, PayrollItem, Account)
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from datetime import datetime


class PayrollService:
    # ── Employee CRUD ──

    @staticmethod
    def create_employee(employee_code, name, department=None, designation=None,
                        email=None, phone=None, date_of_joining=None,
                        bank_account=None, salary_structure_id=None):
        if date_of_joining and isinstance(date_of_joining, str):
            date_of_joining = datetime.strptime(date_of_joining, '%Y-%m-%d').date()
        emp = Employee(
            employee_code=employee_code, name=name,
            department=department, designation=designation,
            email=email, phone=phone,
            date_of_joining=date_of_joining,
            bank_account=bank_account,
            salary_structure_id=int(salary_structure_id) if salary_structure_id else None
        )
        db.session.add(emp)
        db.session.commit()
        AuditService.log(action='CREATE', model='Employee', model_id=emp.id,
                         details=f"Created employee: {employee_code} — {name}")
        return emp

    # ── Salary Component CRUD ──

    @staticmethod
    def create_salary_component(name, component_type, is_statutory=False, account_id=None):
        sc = SalaryComponent(
            name=name, component_type=component_type,
            is_statutory=is_statutory,
            account_id=int(account_id) if account_id else None
        )
        db.session.add(sc)
        db.session.commit()
        return sc

    # ── Salary Structure ──

    @staticmethod
    def create_salary_structure(name, details, description=None):
        """
        details: list of {component_id, amount, percentage, base_component_id}
        """
        ss = SalaryStructure(name=name, description=description)
        db.session.add(ss)
        db.session.flush()

        for d in details:
            ssd = SalaryStructureDetail(
                salary_structure_id=ss.id,
                component_id=int(d['component_id']),
                amount=float(d.get('amount', 0)),
                percentage=float(d.get('percentage', 0)),
                base_component_id=int(d['base_component_id']) if d.get('base_component_id') else None
            )
            db.session.add(ssd)

        db.session.commit()
        return ss

    # ── Payroll Processing ──

    @staticmethod
    def compute_salary(employee):
        """
        Compute component-wise salary for a single employee based on their salary structure.
        Returns: {'gross': float, 'deductions': float, 'net': float, 'components': [...]}
        """
        ss = employee.salary_structure
        if not ss:
            return {'gross': 0, 'deductions': 0, 'net': 0, 'components': []}

        computed = {}  # component_id -> amount
        components = []

        # First pass: compute fixed amounts and earnings
        for detail in ss.details:
            comp = detail.component
            if float(detail.amount) > 0:
                computed[comp.id] = float(detail.amount)
            elif float(detail.percentage) > 0 and detail.base_component_id:
                base_val = computed.get(detail.base_component_id, 0)
                computed[comp.id] = round(base_val * float(detail.percentage) / 100, 2)
            else:
                computed[comp.id] = 0

            components.append({
                'component_id': comp.id,
                'component_name': comp.name,
                'component_type': comp.component_type,
                'amount': computed[comp.id]
            })

        gross = sum(c['amount'] for c in components if c['component_type'] == 'Earning')
        deductions = sum(c['amount'] for c in components if c['component_type'] == 'Deduction')
        net = gross - deductions

        return {
            'gross': round(gross, 2),
            'deductions': round(deductions, 2),
            'net': round(net, 2),
            'components': components
        }

    @staticmethod
    def process_payroll(period, run_date=None):
        """
        Runs payroll for all active employees with a salary structure.
        Returns a PayrollEntry in Draft status.
        """
        if run_date and isinstance(run_date, str):
            run_date = datetime.strptime(run_date, '%Y-%m-%d').date()
        else:
            run_date = datetime.utcnow().date()

        employees = Employee.query.filter_by(is_active=True)\
            .filter(Employee.salary_structure_id.isnot(None)).all()

        entry = PayrollEntry(period=period, run_date=run_date, status='Draft')
        db.session.add(entry)
        db.session.flush()

        total_gross = 0
        total_deductions = 0
        total_net = 0

        for emp in employees:
            result = PayrollService.compute_salary(emp)
            pi = PayrollItem(
                payroll_entry_id=entry.id,
                employee_id=emp.id,
                gross_pay=result['gross'],
                total_deductions=result['deductions'],
                net_pay=result['net'],
                components_json=json.dumps(result['components'])
            )
            db.session.add(pi)
            total_gross += result['gross']
            total_deductions += result['deductions']
            total_net += result['net']

        entry.total_gross = total_gross
        entry.total_deductions = total_deductions
        entry.total_net = total_net

        db.session.commit()
        AuditService.log(action='CREATE', model='PayrollEntry', model_id=entry.id,
                         details=f"Payroll processed for {period}: {len(employees)} employees")
        return entry

    @staticmethod
    def post_payroll(payroll_entry_id):
        """
        Posts the payroll to the GL.
        Dr: Salary Expense (5030)
        Cr: Bank/Cash (1020) for net pay
        Cr: Individual deduction accounts for statutory amounts
        """
        entry = PayrollEntry.query.get(payroll_entry_id)
        if not entry:
            raise ValueError("Payroll entry not found.")
        if entry.status == 'Posted':
            raise ValueError("Payroll already posted.")

        salary_expense = Account.query.filter_by(code='5030').first()
        bank_account = Account.query.filter_by(code='1020').first()

        if not salary_expense or not bank_account:
            raise ValueError("Salary Expense (5030) or Bank (1020) account not found.")

        je_items = [
            {'account_id': salary_expense.id, 'debit': float(entry.total_gross), 'credit': 0}
        ]

        # Aggregate deduction accounts
        deduction_map = {}
        for pi in entry.payroll_items:
            components = json.loads(pi.components_json) if pi.components_json else []
            for comp in components:
                if comp['component_type'] == 'Deduction' and comp['amount'] > 0:
                    sc = SalaryComponent.query.get(comp['component_id'])
                    acc_id = sc.account_id if sc and sc.account_id else None
                    if acc_id:
                        deduction_map[acc_id] = deduction_map.get(acc_id, 0) + comp['amount']

        for acc_id, amount in deduction_map.items():
            je_items.append({'account_id': acc_id, 'debit': 0, 'credit': amount})

        # Net pay → Bank
        total_deduction_posted = sum(deduction_map.values())
        net_to_bank = float(entry.total_gross) - total_deduction_posted
        if net_to_bank > 0:
            je_items.append({'account_id': bank_account.id, 'debit': 0, 'credit': net_to_bank})

        je = AccountingService.create_journal_entry(
            date=entry.run_date,
            description=f"Payroll — {entry.period}",
            items=je_items,
            reference=f"PAYROLL-{entry.id}"
        )
        entry.journal_entry_id = je.id
        entry.status = 'Posted'
        db.session.commit()
        return entry
