# Account Auto Commission Extension

## Purpose

This module extends Odoo 18 Community to automatically assign predefined OCA commission
agents on draft customer invoice lines and quotation lines.

It is designed to keep commission assignment consistent, auditable, and company-aware without hardcoding users or percentages.

## Installation

1. Place the module folder `account_auto_commission_extension` in your custom addons path.
2. Ensure dependencies are installed:
   - `account`
   - `account_commission_oca` (OCA)
   - `sale_commission_oca` (OCA)
3. Update apps list.
4. Install **Account Auto Commission Extension**.

## Configuration

1. Go to **Accounting > Configuration > Settings**.
2. In **Automatic Commission Assignment**, choose **Automatic Commission Agents**.
3. Optionally enable **Automatically assign selected auto-commission agents to all new products**.
4. Save.
5. On each product, define **Commission Agents** that are allowed for that product (or use the automatic product option above).

Notes:
- Only records already configured as OCA commission agents are selectable.
- Configuration is stored per company in `auto.commission.config`.
- Only users in `account.group_account_manager` can modify this configuration.

## How Automation Works

- Hooks:
  - `account.move.line.create()` / `account.move.line.write()`
  - `sale.order.line.create()` / `sale.order.line.write()`
- Scope:
  - Draft customer invoice/refund lines with products
  - Draft/sent quotation lines with products
- Behavior:
  - Loads company-specific configured agents from `auto.commission.config`.
  - Intersects them with product agents (`product.template.commission_agent_ids`).
  - Adds only missing agent entries via OCA helper methods.
  - Never duplicates existing agent lines.
  - Preserves manual commission edits on write operations.

## Product Auto-Assignment Option

- If **Automatically assign selected auto-commission agents to all new products** is enabled:
  - Every newly created product receives missing agents from company auto-commission settings.
  - Existing product agents are preserved (only missing ones are added).
- If disabled:
  - New products are not modified automatically.
  - You can still assign manually on product form.
  - Accounting managers can use **Apply Auto-Commission Agents** button on product form to add missing configured agents.

Commission percentages are not hardcoded and are resolved from existing OCA commission configuration attached to each selected agent.

## Safety and Edge Cases

- Multi-company safe: configuration and commission resolution respect `company_id`.
- Draft invoice + quotation automation: no changes on posted invoices or confirmed sales orders.
- Idempotent behavior: repeated calls do not duplicate lines.
- Graceful fallback:
  - If no config exists, it silently skips.
  - If an agent lacks complete commission setup, that agent is skipped without crashing invoice creation.

## Security Notes

- The persistent configuration model is writable only by accounting managers.
- Internal accounting users have read-only access for runtime automation.
- Sales users have read-only access for quotation runtime automation.
- A company rule restricts access to configuration records within allowed companies.
- No privilege escalation, no global invoice record rules, and no direct SQL are used.

## Upgrade Compatibility

- Built with standard model inheritance and extension points (no monkey patching).
- Keeps OCA commission logic as source of truth for commission definitions.
- Avoids modifying OCA source code.
- Suitable for Docker deployments and CI/CD module updates.

## Known Limitations

- This module assumes OCA `account_commission_oca` and `sale_commission_oca` provide line agent structures compatible with `agent_ids`.
- If OCA internals are heavily customized, automatic assignment may skip lines and log warnings instead of forcing unsafe writes.
