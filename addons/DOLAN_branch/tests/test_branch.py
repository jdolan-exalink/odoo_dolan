from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestBranch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Branch = cls.env['dolan.branch']
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.journal = cls.env['account.journal'].create({'name': 'Ventas Centro', 'code': 'VCEN', 'type': 'general'})
        cls.centro = cls.Branch.create({'name': 'Centro', 'code': 'CEN', 'warehouse_id': cls.warehouse.id,
                                        'journal_ids': [(4, cls.journal.id)]})
        cls.norte = cls.Branch.create({'name': 'Norte', 'code': 'NOR'})
        cls.seller = new_test_user(cls.env, login='vendedora_norte', groups='account.group_account_invoice')
        cls.seller.write({'dolan_branch_ids': [(6, 0, (cls.centro | cls.norte).ids)], 'dolan_branch_id': cls.norte.id})

    def move(self, journal=None, user=None):
        journal = journal or self.env['account.journal'].create({'name': 'Varios sin sucursal', 'code': 'VSS', 'type': 'general'})
        return self.env['account.move'].with_user(user or self.env.user).create({'move_type': 'entry', 'journal_id': journal.id})

    def test_move_takes_branch_from_journal(self):
        self.assertEqual(self.move(self.journal).dolan_branch_id, self.centro)

    def test_move_falls_back_to_user_branch(self):
        # Una factura borrador que arma la vendedora en un diario sin sucursal toma la sucursal de ella.
        journal = self.env['account.journal'].create({'name': 'Ventas sin sucursal', 'code': 'VSSU', 'type': 'sale'})
        partner = self.env['res.partner'].create({'name': 'Cliente Norte'})
        move = self.env['account.move'].with_user(self.seller).create({
            'move_type': 'out_invoice', 'journal_id': journal.id, 'partner_id': partner.id})
        self.assertEqual(move.dolan_branch_id, self.norte)

    def test_picking_takes_branch_from_warehouse(self):
        picking_type = self.warehouse.out_type_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id, 'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id})
        self.assertEqual(picking.dolan_branch_id, self.centro)

    def test_constraints(self):
        with self.assertRaises(ValidationError):
            self.seller.dolan_branch_id = self.Branch.create({'name': 'Sur', 'code': 'SUR'})
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Branch.create({'name': 'Duplicada', 'code': 'CEN'})
            self.env.flush_all()

    def test_branch_counts_moves(self):
        self.move(self.journal)
        self.centro.invalidate_recordset(['move_count'])
        self.assertEqual(self.centro.move_count, 1)
