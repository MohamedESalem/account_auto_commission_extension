# -*- coding: utf-8 -*-
{
    "name": "Account Auto Commission Extension",
    "summary": "Automatically assign configured OCA commission agents on draft customer invoice lines",
    "version": "18.0.2.0.0",
    "category": "Accounting",
    "author": "Essam Salem Law Firm",
    "license": "LGPL-3",
    "depends": [
        "account",
        "account_commission_oca",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/product_template_views.xml",
        "views/auto_commission_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
