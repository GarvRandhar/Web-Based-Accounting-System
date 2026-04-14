from app.extensions import db
from app.models import Tax, TaxGroup, TaxGroupItem
from app.services.audit import AuditService


class TaxationService:
    @staticmethod
    def create_tax_group(name, tax_ids, description=None):
        """
        Creates a composite tax group (e.g. GST 18% = CGST 9% + SGST 9%).
        tax_ids: ordered list of Tax IDs that make up the group.
        """
        group = TaxGroup(name=name, description=description)
        db.session.add(group)
        db.session.flush()

        for seq, tax_id in enumerate(tax_ids):
            item = TaxGroupItem(
                tax_group_id=group.id,
                tax_id=int(tax_id),
                sequence=seq
            )
            db.session.add(item)

        db.session.commit()
        AuditService.log(action='CREATE', model='TaxGroup', model_id=group.id,
                         details=f"Created tax group: {name}")
        return group

    @staticmethod
    def delete_tax_group(group_id):
        group = db.session.get(TaxGroup, group_id)
        if group:
            group.is_active = False
            db.session.commit()
            AuditService.log(action='DELETE', model='TaxGroup', model_id=group.id,
                             details=f"Deactivated tax group: {group.name}")
        return group

    @staticmethod
    def calculate_tax_group(group_id, base_amount):
        """
        Returns a breakdown of each component tax for a given base amount.
        [{'tax_name': 'CGST', 'rate': 9.0, 'amount': 900.0, 'account_id': 5}, ...]
        """
        group = db.session.get(TaxGroup, group_id)
        if not group:
            return []

        breakdown = []
        for gi in group.items:
            tax = gi.tax
            if not tax:
                continue
            amount = float(base_amount) * float(tax.rate) / 100
            breakdown.append({
                'tax_id': tax.id,
                'tax_name': tax.name,
                'rate': float(tax.rate),
                'amount': round(amount, 2),
                'sales_account_id': tax.sales_tax_account_id,
                'purchase_account_id': tax.purchase_tax_account_id
            })
        return breakdown

    @staticmethod
    def get_total_tax(group_id, base_amount):
        breakdown = TaxationService.calculate_tax_group(group_id, base_amount)
        return sum(item['amount'] for item in breakdown)
