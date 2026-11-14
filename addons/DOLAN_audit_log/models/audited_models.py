"""Modelos que se auditan. Qué campos y operaciones se registran lo deciden las reglas (data/audit_rules.xml)."""
from odoo import models


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'dolan.audit.mixin']


class ResPartnerBank(models.Model):
    _name = 'res.partner.bank'
    _inherit = ['res.partner.bank', 'dolan.audit.mixin']


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'dolan.audit.mixin']


class ProductPricelistItem(models.Model):
    _name = 'product.pricelist.item'
    _inherit = ['product.pricelist.item', 'dolan.audit.mixin']


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'dolan.audit.mixin']


class AccountPayment(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment', 'dolan.audit.mixin']


class AccountPartialReconcile(models.Model):
    _name = 'account.partial.reconcile'
    _inherit = ['account.partial.reconcile', 'dolan.audit.mixin']


class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users', 'dolan.audit.mixin']
