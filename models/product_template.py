# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    commission_agent_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="product_tmpl_commission_agent_rel",
        column1="product_tmpl_id",
        column2="agent_id",
        string="Commission Agents",
        domain=[("agent", "=", True)],
        help=(
            "Agents that can be auto-assigned on draft invoice lines for this product. "
            "Only agents also selected in Automatic Commission settings are applied."
        ),
    )
