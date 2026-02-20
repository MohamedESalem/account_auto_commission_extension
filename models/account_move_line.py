# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends(
        "move_id.partner_id",
        "move_id.state",
        "move_id.move_type",
        "product_id",
        "product_id.commission_agent_ids",
        "display_type",
        "company_id",
        "commission_free",
    )
    def _compute_agent_ids(self):
        super()._compute_agent_ids()
        # OCA computes from partner agents; enforce product/config intersection afterward.
        self.filtered(lambda line: line.id)._auto_sync_commission_agents(
            strict=False, skip_manual=True
        )

    @api.model
    def _auto_has_explicit_agent_commands(self, vals):
        commands = vals.get("agent_ids")
        if not commands:
            return False

        for command in commands:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            operation = command[0]
            if operation in (0, 1, 2, 3, 4):
                return True
            if operation == 6:
                ids = command[2] if len(command) > 2 else []
                if ids:
                    return True
        return False

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line, vals in zip(lines, vals_list):
            if self._auto_has_explicit_agent_commands(vals):
                _logger.debug(
                    "Skipping auto commission sync on line %s due to explicit non-empty agent commands in create vals.",
                    line.id,
                )
                continue
            line._auto_sync_commission_agents(strict=True, skip_manual=False)
        return lines

    def write(self, vals):
        tracked_fields = {"product_id", "quantity", "price_unit", "discount", "display_type", "move_id"}
        should_sync = bool(tracked_fields.intersection(vals))
        has_manual_agent_commands = self._auto_has_explicit_agent_commands(vals)

        result = super().write(vals)

        if not should_sync:
            return result
        if has_manual_agent_commands:
            _logger.debug(
                "Skipping auto commission sync on lines %s due to manual agent_ids write.",
                self.ids,
            )
            return result

        self._auto_sync_commission_agents(strict=False, skip_manual=True)
        return result

    def _auto_is_target_line(self):
        self.ensure_one()
        if not self.move_id:
            _logger.debug("Line %s skipped: no move_id.", self.id)
            return False
        if self.move_id.state != "draft":
            _logger.debug("Line %s skipped: move %s is not draft.", self.id, self.move_id.id)
            return False
        if self.move_id.move_type not in ("out_invoice", "out_refund"):
            _logger.debug(
                "Line %s skipped: move %s type %s is not customer invoice/refund.",
                self.id,
                self.move_id.id,
                self.move_id.move_type,
            )
            return False
        if not self.product_id:
            _logger.debug("Line %s skipped: no product_id.", self.id)
            return False
        if self.display_type and self.display_type != "product":
            _logger.debug(
                "Line %s skipped: non-product display line (%s).",
                self.id,
                self.display_type,
            )
            return False
        return True

    def _auto_get_target_agents(self, config):
        self.ensure_one()

        if not config or not config.commission_agent_ids:
            _logger.debug(
                "Line %s skipped: no auto commission config or empty configured agents for company %s.",
                self.id,
                self.company_id.id,
            )
            return self.env["res.partner"]

        product_agents = self.product_id.commission_agent_ids
        if not product_agents:
            _logger.debug(
                "Line %s skipped: product %s has no commission agents.",
                self.id,
                self.product_id.id,
            )
            return self.env["res.partner"]

        target_agents = product_agents & config.commission_agent_ids
        target_agents = target_agents.filtered(lambda agent: agent.agent and bool(agent.commission_id))
        if "company_id" in target_agents._fields:
            target_agents = target_agents.filtered(
                lambda agent: not agent.company_id or agent.company_id == self.company_id
            )
        return target_agents

    def _auto_sync_commission_agents(self, strict=False, skip_manual=False):
        if not self:
            return

        target_lines = self.filtered(lambda line: line._auto_is_target_line())
        if not target_lines:
            return

        configs = self.env["auto.commission.config"].search(
            [("company_id", "in", target_lines.mapped("company_id").ids)]
        )
        config_by_company = {config.company_id.id: config for config in configs}
        agent_line_model = self.env["account.invoice.line.agent"]

        for line in target_lines:
            config = config_by_company.get(line.company_id.id)
            target_agents = line._auto_get_target_agents(config)
            target_agent_ids = set(target_agents.ids)

            if strict:
                stale_lines = line.agent_ids.filtered(
                    lambda agent_line: agent_line.agent_id.id not in target_agent_ids
                )
            else:
                stale_lines = line.agent_ids.filtered(
                    lambda agent_line: (
                        agent_line.auto_commission_managed
                        and agent_line.agent_id.id not in target_agent_ids
                    )
                )
            if stale_lines:
                _logger.debug(
                    "Line %s removing stale auto commission lines: %s",
                    line.id,
                    stale_lines.ids,
                )
                stale_lines.unlink()

            existing_by_agent = {agent_line.agent_id.id: agent_line for agent_line in line.agent_ids}
            to_create = []
            for agent in target_agents:
                existing_line = existing_by_agent.get(agent.id)
                if existing_line:
                    if strict and not skip_manual and not existing_line.auto_commission_managed:
                        existing_line.auto_commission_managed = True
                    continue

                vals = line._prepare_agent_vals(agent)
                vals["object_id"] = line.id
                vals["auto_commission_managed"] = True
                to_create.append(vals)

            if to_create:
                _logger.debug("Line %s creating auto commission lines: %s", line.id, to_create)
                agent_line_model.create(to_create)
