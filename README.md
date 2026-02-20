# Account Auto Commission Extension

## Purpose

This module extends Odoo 18 Community to automatically assign predefined OCA commission
agents when draft customer invoice lines are created or updated (`account.move.line`).

It is designed to keep commission assignment consistent, auditable, and company-aware without hardcoding users or percentages.

## Installation

1. Place the module folder `account_auto_commission_extension` in your custom addons path.
2. Ensure dependencies are installed:
   - `account`
   - `account_commission_oca` (OCA)
3. Update apps list.
4. Install **Account Auto Commission Extension**.

## Configuration

1. Go to **Accounting > Configuration > Settings**.
2. In **Automatic Commission Assignment**, choose **Automatic Commission Agents**.
3. Save.
4. On each product, define **Commission Agents** that are allowed for that product.

Notes:
- Only records already configured as OCA commission agents are selectable.
- Configuration is stored per company in `auto.commission.config`.
- Only users in `account.group_account_manager` can modify this configuration.

## How Automation Works

- Hook: `account.move.line.create()` and `account.move.line.write()`.
- Scope: draft customer invoice/refund lines with products (`move_type in ('out_invoice', 'out_refund')`, `state = draft`).
- Behavior:
  - Loads company-specific configured agents from `auto.commission.config`.
  - Intersects them with product agents (`product.template.commission_agent_ids`).
  - Adds only missing agent entries via OCA helper methods.
  - Never duplicates existing agent lines.
  - Preserves manual commission edits on write operations.

Commission percentages are not hardcoded and are resolved from existing OCA commission configuration attached to each selected agent.

## Safety and Edge Cases

- Multi-company safe: configuration and commission resolution respect `company_id`.
- Draft-only automation: no changes on posted invoices.
- Idempotent behavior: repeated calls do not duplicate lines.
- Graceful fallback:
  - If no config exists, it silently skips.
  - If an agent lacks complete commission setup, that agent is skipped without crashing invoice creation.

## Security Notes

- The persistent configuration model is writable only by accounting managers.
- Internal accounting users have read-only access for runtime automation.
- A company rule restricts access to configuration records within allowed companies.
- No privilege escalation, no global invoice record rules, and no direct SQL are used.

## Upgrade Compatibility

- Built with standard model inheritance and extension points (no monkey patching).
- Keeps OCA commission logic as source of truth for commission definitions.
- Avoids modifying OCA source code.
- Suitable for Docker deployments and CI/CD module updates.

## Known Limitations

- This module assumes OCA `account_commission` provides invoice line agent structures compatible with `agent_ids`.
- If OCA internals are heavily customized, automatic assignment may skip lines and log warnings instead of forcing unsafe writes.
