# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


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

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._auto_apply_selected_commission_agents(force=False, raise_if_error=False)
        return templates

    def action_apply_auto_commission_agents(self):
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError("Only accounting managers can apply auto-commission agents.")
        self._auto_apply_selected_commission_agents(force=True, raise_if_error=True)
        return True

    def _auto_apply_selected_commission_agents(self, force=False, raise_if_error=False):
        if not self:
            return

        config_model = self.env["auto.commission.config"].sudo()
        company_ids = {
            (template.company_id or self.env.company).id
            for template in self
        }
        configs = config_model.search([("company_id", "in", list(company_ids))])
        config_by_company = {config.company_id.id: config for config in configs}

        for template in self:
            company = template.company_id or self.env.company
            config = config_by_company.get(company.id)
            if not config:
                _logger.debug(
                    "Skipping auto-assign on product %s: no auto commission config for company %s.",
                    template.id,
                    company.id,
                )
                continue
            if not force and not config.auto_assign_agents_to_new_products:
                continue
            if not config.commission_agent_ids:
                continue

            target_agents = config.commission_agent_ids.filtered(
                lambda agent: (
                    agent.agent
                    and bool(agent.commission_id)
                    and (
                        "company_id" not in agent._fields
                        or not agent.company_id
                        or agent.company_id == company
                    )
                )
            )
            if not target_agents:
                continue

            missing_agents = target_agents - template.commission_agent_ids
            if not missing_agents:
                continue

            try:
                template.commission_agent_ids = [(4, agent_id) for agent_id in missing_agents.ids]
                _logger.debug(
                    "Applied auto-commission agents to product %s: added %s",
                    template.id,
                    missing_agents.ids,
                )
            except (AccessError, UserError, ValidationError) as err:
                _logger.debug(
                    "Skipping auto-assign on product %s due to access/validation error: %s",
                    template.id,
                    err,
                )
                if raise_if_error:
                    raise
