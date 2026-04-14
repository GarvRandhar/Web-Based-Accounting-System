from app.extensions import db
from app.models import CostCenter, JournalItem, JournalEntry, Account
from app.services.audit import AuditService
from sqlalchemy import func


class CostCenterService:
    @staticmethod
    def create_cost_center(code, name, description=None, parent_id=None):
        cc = CostCenter(code=code, name=name, description=description, parent_id=parent_id)
        db.session.add(cc)
        db.session.commit()
        AuditService.log(action='CREATE', model='CostCenter', model_id=cc.id,
                         details=f"Created cost center: {code} - {name}")
        return cc

    @staticmethod
    def update_cost_center(cc_id, **kwargs):
        cc = db.session.get(CostCenter, cc_id)
        if not cc:
            raise ValueError("Cost center not found.")
        for k, v in kwargs.items():
            if hasattr(cc, k):
                setattr(cc, k, v)
        db.session.commit()
        return cc

    @staticmethod
    def deactivate_cost_center(cc_id):
        cc = db.session.get(CostCenter, cc_id)
        if cc:
            cc.is_active = False
            db.session.commit()
        return cc

    @staticmethod
    def get_pl_by_cost_center(cost_center_id, start_date=None, end_date=None):
        """
        Generates a mini Profit & Loss filtered by a specific cost center.
        Returns revenue, expenses, and net income for that cost center.
        """
        def get_balance(acc_type):
            q = db.session.query(
                Account.name,
                Account.code,
                func.sum(JournalItem.debit).label('total_debit'),
                func.sum(JournalItem.credit).label('total_credit')
            ).join(Account, JournalItem.account_id == Account.id)\
             .join(JournalEntry, JournalItem.journal_entry_id == JournalEntry.id)\
             .filter(Account.type == acc_type)\
             .filter(JournalItem.cost_center_id == cost_center_id)

            if start_date:
                q = q.filter(JournalEntry.date >= start_date)
            if end_date:
                q = q.filter(JournalEntry.date <= end_date)

            q = q.group_by(Account.id)
            rows = q.all()

            details = []
            total = 0
            for name, code, dr, cr in rows:
                dr = float(dr or 0)
                cr = float(cr or 0)
                bal = (cr - dr) if acc_type == 'Revenue' else (dr - cr)
                if abs(bal) > 0.01:
                    details.append({'code': code, 'name': name, 'balance': bal})
                    total += bal
            return {'total': total, 'accounts': details}

        revenue = get_balance('Revenue')
        expenses = get_balance('Expense')
        return {
            'revenue': revenue,
            'expenses': expenses,
            'net_income': revenue['total'] - expenses['total']
        }
