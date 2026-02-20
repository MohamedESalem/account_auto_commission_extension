# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLineAgent(models.Model):
    _inherit = "sale.order.line.agent"

    auto_commission_managed = fields.Boolean(
        string="Auto Commission Managed",
        default=False,
        index=True,
        copy=False,
        help=(
            "Technical flag used by account_auto_commission_extension to identify "
            "agent lines managed automatically from product + settings intersection."
        ),
    )
