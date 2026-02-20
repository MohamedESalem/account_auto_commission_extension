# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)


class AutoCommissionConfig(models.Model):
    """Persistent company-level configuration for auto commission assignment."""

    _name = "auto.commission.config"
    _description = "Automatic Commission Configuration"
    _rec_name = "company_id"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="cascade",
    )
    commission_agent_ids = fields.Many2many(
        "res.partner",
        "auto_commission_config_partner_rel",
        "config_id",
        "partner_id",
        string="Commission Agents",
        domain="[('agent', '=', True)]",
        help=(
            "Agents already configured in OCA commission that can be auto-added on "
            "draft quotation/invoice lines."
        ),
    )

    _sql_constraints = [
        (
            "auto_commission_config_company_uniq",
            "unique(company_id)",
            "Only one automatic commission configuration is allowed per company.",
        )
    ]

    @api.model
    def get_company_config(self, company):
        """Return the configuration record for a company if it exists."""
        return self.search([("company_id", "=", company.id)], limit=1)

    @api.constrains("commission_agent_ids", "company_id")
    def _check_agents_have_commission_setup(self):
        """Allow only agents that already have OCA commission configuration."""
        for config in self:
            invalid_agents = config.commission_agent_ids.filtered(
                lambda partner: not config._agent_has_commission_setup(partner)
            )
            if invalid_agents:
                raise ValidationError(
                    _(
                        "The following agents do not have a valid commission setup: %s"
                    )
                    % ", ".join(invalid_agents.mapped("display_name"))
                )

    def _agent_has_commission_setup(self, partner):
        """Check commission setup defensively across OCA variations."""
        self.ensure_one()

        if "agent" in partner._fields and not partner.agent:
            return False

        if "commission_id" in partner._fields and partner.commission_id:
            return True

        if "commission_ids" in partner._fields and partner.commission_ids:
            commission_lines = partner.commission_ids
            if "company_id" in commission_lines._fields:
                commission_lines = commission_lines.filtered(
                    lambda rec: not rec.company_id or rec.company_id == self.company_id
                )
            if "commission_id" in commission_lines._fields:
                return bool(commission_lines.mapped("commission_id"))
            return bool(commission_lines)

        if "agent_ids" in partner._fields and partner.agent_ids:
            agent_lines = partner.agent_ids
            if "company_id" in agent_lines._fields:
                agent_lines = agent_lines.filtered(
                    lambda rec: not rec.company_id or rec.company_id == self.company_id
                )
            if "commission_id" in agent_lines._fields:
                return bool(agent_lines.mapped("commission_id"))
            return bool(agent_lines)

        return False


class ResConfigSettings(models.TransientModel):
    """Expose automatic commission configuration inside Accounting settings."""

    _inherit = "res.config.settings"

    auto_commission_agent_ids = fields.Many2many(
        "res.partner",
        string="Automatic Commission Agents",
        domain="[('agent', '=', True)]",
        help="Agents allowed for automatic assignment on draft quotation/invoice lines.",
    )

    @api.model
    def get_values(self):
        """Load selected commission agents from company configuration."""
        res = super().get_values()
        company = self.env.company
        config = self.env["auto.commission.config"].get_company_config(company)
        res.update(
            auto_commission_agent_ids=[(6, 0, config.commission_agent_ids.ids if config else [])]
        )
        return res

    def set_values(self):
        """Persist selected commission agents in company configuration."""
        super().set_values()
        if not self.user_has_groups("account.group_account_manager"):
            raise AccessError("Only accounting managers can modify automatic commission settings.")

        config_model = self.env["auto.commission.config"]
        for settings in self:
            company = settings.company_id or self.env.company
            config = config_model.get_company_config(company)
            if not config:
                config = config_model.create({"company_id": company.id})
            config.commission_agent_ids = [(6, 0, settings.auto_commission_agent_ids.ids)]
            _logger.debug(
                "Updated automatic commission agents for company %s: %s",
                company.id,
                settings.auto_commission_agent_ids.ids,
            )

    def user_has_groups(self, groups):
        """Compatibility helper for stacks where this helper is unavailable."""
        return self.env.user.has_group(groups)
