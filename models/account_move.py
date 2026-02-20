# -*- coding: utf-8 -*-
import logging

from odoo import api, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Assign configured commission agents on draft customer invoices."""

    _inherit = "account.move"

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-add missing commission agents on newly created draft customer invoices."""
        moves = super().create(vals_list)
        moves._auto_apply_configured_commission_agents()
        return moves

    def write(self, vals):
        """Apply auto commission when new invoice lines are added to draft invoices."""
        line_commands_changed = any(key in vals for key in ("invoice_line_ids", "line_ids"))
        previous_line_ids = {}

        if line_commands_changed:
            for move in self.filtered(
                lambda m: m.move_type == "out_invoice" and m.state == "draft" and bool(m.company_id)
            ):
                previous_line_ids[move.id] = set(move.invoice_line_ids.ids)

        result = super().write(vals)

        if not line_commands_changed or not previous_line_ids:
            return result

        for move in self.filtered(lambda m: m.id in previous_line_ids):
            new_lines = move.invoice_line_ids.filtered(
                lambda line: line.id not in previous_line_ids[move.id]
            )
            move._auto_apply_configured_commission_agents(invoice_lines=new_lines)

        return result

    def _auto_apply_configured_commission_agents(self, invoice_lines=None):
        """Load company configuration and apply missing agents."""
        target_moves = self.filtered(
            lambda move: move.move_type == "out_invoice"
            and move.state == "draft"
            and bool(move.company_id)
        )
        if not target_moves:
            return

        config_model = self.env["auto.commission.config"].sudo()
        configs = config_model.search([("company_id", "in", target_moves.company_id.ids)])
        configs_by_company = {config.company_id.id: config for config in configs}

        for move in target_moves:
            config = configs_by_company.get(move.company_id.id)
            if not config or not config.commission_agent_ids:
                continue
            move._auto_assign_missing_commission_agents(
                configured_agents=config.commission_agent_ids,
                invoice_lines=invoice_lines if move in self else None,
            )

    def _auto_assign_missing_commission_agents(self, configured_agents, invoice_lines=None):
        """Create only missing agent lines for each invoice line.

        This method is idempotent and keeps existing manual commission lines untouched.
        """
        self.ensure_one()

        if invoice_lines is None:
            invoice_lines = self.invoice_line_ids
        invoice_lines = invoice_lines.filtered(
            lambda line: line.move_id == self and not line.display_type
        )
        if not invoice_lines:
            return

        agent_field = invoice_lines._fields.get("agent_ids")
        if not agent_field:
            _logger.debug(
                "Invoice line model has no agent_ids field; skipping auto commission for move %s",
                self.id,
            )
            return

        agent_line_model = self.env[agent_field.comodel_name]
        inverse_name = agent_field.inverse_name

        if "agent_id" not in agent_line_model._fields:
            _logger.warning(
                "Agent line model %s has no agent_id field; skipping move %s",
                agent_line_model._name,
                self.id,
            )
            return

        for line in invoice_lines:
            existing_agent_ids = set(line.agent_ids.mapped("agent_id").ids)
            to_create = []

            for agent in configured_agents:
                if agent.id in existing_agent_ids:
                    continue

                # Keep multi-company consistency when agent is company-specific.
                if (
                    "company_id" in agent._fields
                    and agent.company_id
                    and agent.company_id != self.company_id
                ):
                    continue

                vals = {
                    inverse_name: line.id,
                    "agent_id": agent.id,
                }

                if "commission_id" in agent_line_model._fields:
                    commission = self._auto_get_commission_for_agent(agent)
                    if not commission:
                        _logger.info(
                            "Skipping agent %s on move %s line %s due to missing commission setup",
                            agent.id,
                            self.id,
                            line.id,
                        )
                        continue
                    vals["commission_id"] = commission.id

                to_create.append(vals)

            if not to_create:
                continue

            try:
                agent_line_model.create(to_create)
            except (AccessError, UserError, ValidationError) as err:
                _logger.warning(
                    "Auto commission assignment skipped for move %s line %s due to validation/access issue: %s",
                    self.id,
                    line.id,
                    err,
                )

    def _auto_get_commission_for_agent(self, agent):
        """Resolve agent commission from OCA commission configuration.

        The method is defensive to avoid crashes across minor OCA variations.
        """
        commission_candidates = self.env["commission"]

        if "commission_id" in agent._fields and agent.commission_id:
            commission_candidates |= agent.commission_id

        if "commission_ids" in agent._fields and agent.commission_ids:
            commissions = agent.commission_ids
            if "company_id" in commissions._fields:
                commissions = commissions.filtered(
                    lambda rec: not rec.company_id or rec.company_id == self.company_id
                )

            if "commission_id" in commissions._fields:
                commission_candidates |= commissions.mapped("commission_id")
            elif commissions._name == "commission":
                commission_candidates |= commissions

        if not commission_candidates:
            return False

        if "company_id" in commission_candidates._fields:
            commission_candidates = commission_candidates.filtered(
                lambda rec: not rec.company_id or rec.company_id == self.company_id
            )

        return commission_candidates[:1]
