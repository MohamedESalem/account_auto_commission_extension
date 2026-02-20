# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def write(self, vals):
        should_sync = "order_line" in vals
        result = super().write(vals)

        if not should_sync:
            return result

        orders_to_sync = self.filtered(lambda order: order.state in ("draft", "sent"))
        if not orders_to_sync:
            return result

        _logger.debug(
            "Fallback quotation-level auto commission sync for orders: %s",
            orders_to_sync.ids,
        )
        orders_to_sync.mapped("order_line")._auto_sync_commission_agents(
            strict=False, skip_manual=True
        )
        return result
