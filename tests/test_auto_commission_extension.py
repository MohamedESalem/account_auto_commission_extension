# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAutoCommissionExtension(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env.ref("base.res_partner_2")
        cls.partner.agent_ids = [(5, 0, 0)]

        cls.income_account = cls.env["account.account"].search(
            [
                ("company_ids", "in", cls.company.id),
                ("account_type", "=", "income"),
            ],
            limit=1,
        )

        cls.commission_a = cls.env["commission"].create(
            {
                "name": "Auto Commission A",
                "fix_qty": 10.0,
            }
        )
        cls.commission_b = cls.env["commission"].create(
            {
                "name": "Auto Commission B",
                "fix_qty": 15.0,
            }
        )
        cls.commission_c = cls.env["commission"].create(
            {
                "name": "Auto Commission C",
                "fix_qty": 20.0,
            }
        )

        cls.agent_a = cls.env["res.partner"].create(
            {
                "name": "Auto Agent A",
                "agent": True,
                "settlement": "monthly",
                "commission_id": cls.commission_a.id,
            }
        )
        cls.agent_b = cls.env["res.partner"].create(
            {
                "name": "Auto Agent B",
                "agent": True,
                "settlement": "monthly",
                "commission_id": cls.commission_b.id,
            }
        )
        cls.agent_c = cls.env["res.partner"].create(
            {
                "name": "Auto Agent C",
                "agent": True,
                "settlement": "monthly",
                "commission_id": cls.commission_c.id,
            }
        )

        cls.product_ab = cls.env["product.product"].create(
            {
                "name": "Product AB",
                "type": "service",
                "commission_agent_ids": [(6, 0, [cls.agent_a.id, cls.agent_b.id])],
            }
        )
        cls.product_a = cls.env["product.product"].create(
            {
                "name": "Product A",
                "type": "service",
                "commission_agent_ids": [(6, 0, [cls.agent_a.id])],
            }
        )
        cls.product_b = cls.env["product.product"].create(
            {
                "name": "Product B",
                "type": "service",
                "commission_agent_ids": [(6, 0, [cls.agent_b.id])],
            }
        )
        cls.product_ac = cls.env["product.product"].create(
            {
                "name": "Product AC",
                "type": "service",
                "commission_agent_ids": [(6, 0, [cls.agent_a.id, cls.agent_c.id])],
            }
        )

    def _set_config(self, agents, company=None):
        company = company or self.company
        config_model = self.env["auto.commission.config"]
        config = config_model.search([("company_id", "=", company.id)], limit=1)
        if not config:
            config = config_model.create({"company_id": company.id})
        config.commission_agent_ids = [(6, 0, agents.ids)]
        return config

    def _create_invoice(self, product=None, user=None):
        move_model = self.env["account.move"]
        if user:
            move_model = move_model.with_user(user).with_company(self.company)

        line_vals = {
            "name": "Line",
            "quantity": 1.0,
            "price_unit": 100.0,
            "account_id": self.income_account.id,
        }
        if product:
            line_vals["product_id"] = product.id

        invoice = move_model.create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_line_ids": [(0, 0, line_vals)],
            }
        )
        return invoice, invoice.invoice_line_ids[:1]

    def test_create_line_assigns_intersection_only(self):
        self._set_config(self.agent_a | self.agent_c)
        _, line = self._create_invoice(product=self.product_ab)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})
        self.assertTrue(all(line.agent_ids.mapped("auto_commission_managed")))

    def test_create_line_no_config_no_crash(self):
        self._set_config(self.env["res.partner"])
        _, line = self._create_invoice(product=self.product_a)
        self.assertFalse(line.agent_ids)

    def test_write_product_adds_agents(self):
        self._set_config(self.agent_a)
        _, line = self._create_invoice(product=None)
        self.assertFalse(line.agent_ids)

        line.write({"product_id": self.product_a.id})
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_write_qty_price_idempotent_no_duplicates(self):
        self._set_config(self.agent_a)
        _, line = self._create_invoice(product=self.product_a)

        line.write({"quantity": 2.0})
        line.write({"price_unit": 150.0})
        line.write({"discount": 5.0})

        agent_lines = line.agent_ids.filtered(lambda l: l.agent_id == self.agent_a)
        self.assertEqual(len(agent_lines), 1)

    def test_create_with_empty_agent_commands_still_assigns(self):
        self._set_config(self.agent_a)
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Line With Empty Commands",
                            "product_id": self.product_a.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.income_account.id,
                            "agent_ids": [(6, 0, [])],
                        },
                    )
                ],
            }
        )
        line = move.invoice_line_ids[:1]
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_write_with_empty_agent_commands_still_assigns(self):
        self._set_config(self.agent_a)
        _, line = self._create_invoice(product=None)
        self.assertFalse(line.agent_ids)

        line.write({"product_id": self.product_a.id, "agent_ids": [(6, 0, [])]})
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_write_with_clear_only_agent_commands_still_assigns(self):
        self._set_config(self.agent_a)
        _, line = self._create_invoice(product=None)
        self.assertFalse(line.agent_ids)

        line.write({"product_id": self.product_a.id, "agent_ids": [(5, 0, 0)]})
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_product_change_replaces_only_auto_managed(self):
        self._set_config(self.agent_a | self.agent_b | self.agent_c)
        _, line = self._create_invoice(product=self.product_a)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})
        self.assertTrue(all(line.agent_ids.mapped("auto_commission_managed")))

        line.write(
            {
                "agent_ids": [
                    (
                        0,
                        0,
                        {
                            "agent_id": self.agent_c.id,
                            "commission_id": self.agent_c.commission_id.id,
                        },
                    )
                ]
            }
        )
        manual_line = line.agent_ids.filtered(lambda l: l.agent_id == self.agent_c)
        self.assertFalse(manual_line.auto_commission_managed)

        line.write({"product_id": self.product_b.id})

        self.assertEqual(
            set(line.agent_ids.mapped("agent_id").ids),
            {self.agent_b.id, self.agent_c.id},
        )
        auto_b = line.agent_ids.filtered(lambda l: l.agent_id == self.agent_b)
        self.assertTrue(auto_b.auto_commission_managed)
        self.assertFalse(line.agent_ids.filtered(lambda l: l.agent_id == self.agent_a))

    def test_posted_invoice_ignored(self):
        self._set_config(self.agent_a | self.agent_b)
        invoice, line = self._create_invoice(product=self.product_a)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

        invoice.action_post()
        line._auto_sync_commission_agents(strict=False, skip_manual=True)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_invoice_post_keeps_agents(self):
        self._set_config(self.agent_a)
        invoice, line = self._create_invoice(product=self.product_a)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})
        invoice.action_post()
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_partner_recompute_does_not_drop_auto_agents(self):
        self._set_config(self.agent_a)
        other_partner = self.env["res.partner"].create({"name": "No Agent Partner"})
        invoice, line = self._create_invoice(product=self.product_a)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

        invoice.partner_id = other_partner
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_display_type_product_is_not_skipped(self):
        self._set_config(self.agent_a)
        _, line = self._create_invoice(product=self.product_a)

        display_type_selection = dict(line._fields["display_type"].selection or [])
        if "product" in display_type_selection:
            line.display_type = "product"
            line._auto_sync_commission_agents(strict=False, skip_manual=True)

        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_move_write_fallback_syncs_new_lines(self):
        self._set_config(self.agent_a)
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
            }
        )
        move.write(
            {
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Fallback Line",
                            "product_id": self.product_a.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.income_account.id,
                            "agent_ids": [(5, 0, 0)],
                        },
                    )
                ]
            }
        )
        line = move.invoice_line_ids[:1]
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_quotation_line_assigns_intersection_only(self):
        self._set_config(self.agent_a | self.agent_c)
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "name": "Quotation line",
                "product_id": self.product_ab.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_quotation_write_product_assigns_agents(self):
        self._set_config(self.agent_a)
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "name": "No product yet",
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        self.assertFalse(line.agent_ids)
        line.write({"product_id": self.product_a.id})
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_quotation_confirm_keeps_agents(self):
        self._set_config(self.agent_a)
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "name": "Confirm keep line",
                "product_id": self.product_a.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})
        order.action_confirm()
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_quotation_sale_user_runtime_no_sudo_needed(self):
        self._set_config(self.agent_a)
        sale_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Auto Commission Salesman",
                "login": "auto_commission_sale_user",
                "email": "auto_commission_sale_user@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("sales_team.group_sale_salesman").id,
                        ],
                    )
                ],
            }
        )
        sale_order = self.env["sale.order"].with_user(sale_user).with_company(self.company).create(
            {"partner_id": self.partner.id}
        )
        line = self.env["sale.order.line"].with_user(sale_user).with_company(self.company).create(
            {
                "order_id": sale_order.id,
                "name": "Sale user line",
                "product_id": self.product_a.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            }
        )
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_multi_company_config_isolated(self):
        company_2 = self.env["res.company"].create({"name": "Auto Commission Company 2"})
        self._set_config(self.agent_a, company=self.company)
        self._set_config(self.agent_b, company=company_2)

        _, line = self._create_invoice(product=self.product_ab)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})

    def test_non_manager_runtime_no_sudo_needed(self):
        self._set_config(self.agent_a)
        account_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Auto Commission Accountant",
                "login": "auto_commission_account_user",
                "email": "auto_commission_account_user@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("account.group_account_user").id,
                        ],
                    )
                ],
            }
        )

        _, line = self._create_invoice(product=self.product_a, user=account_user)
        self.assertEqual(set(line.agent_ids.mapped("agent_id").ids), {self.agent_a.id})
