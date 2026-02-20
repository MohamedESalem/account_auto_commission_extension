# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def write(self, vals):
        should_sync = bool({"invoice_line_ids", "line_ids"}.intersection(vals))
        result = super().write(vals)

        if not should_sync:
            return result

        moves_to_sync = self.filtered(
            lambda move: move.state == "draft" and move.move_type in ("out_invoice", "out_refund")
        )
        if not moves_to_sync:
            return result

        _logger.debug(
            "Fallback move-level auto commission sync for moves: %s",
            moves_to_sync.ids,
        )
        moves_to_sync.mapped("invoice_line_ids")._auto_sync_commission_agents(
            strict=False, skip_manual=True
        )
        return result
