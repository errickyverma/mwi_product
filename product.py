# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv
from openerp.tools.translate import _
from openerp.tools.safe_eval import safe_eval as eval
import openerp.addons.decimal_precision as dp

class product_product(osv.osv):
    _inherit = "product.product"
        

    def view_header_get(self, cr, user, view_id, view_type, context=None):
        if context is None:
            context = {}
        res = super(product_product, self).view_header_get(cr, user, view_id, view_type, context)
        if res: return res
        if (context.get('active_id', False)) and (context.get('active_model') == 'stock.location'):
            return _('Products: ')+self.pool.get('stock.location').browse(cr, user, context['active_id'], context).name
        return res

    def _get_domain_locations(self, cr, uid, ids, context=None):
        '''
        Parses the context and returns a list of location_ids based on it.
        It will return all stock locations when no parameters are given
        Possible parameters are shop, warehouse, location, force_company, compute_child
        '''
        context = context or {}

        location_obj = self.pool.get('stock.location')
        warehouse_obj = self.pool.get('stock.warehouse')

        location_ids = []
        if context.get('location', False):
            if type(context['location']) == type(1):
                location_ids = [context['location']]
            elif type(context['location']) in (type(''), type(u'')):
                domain = [('complete_name','ilike',context['location'])]
                if context.get('force_company', False):
                    domain += [('company_id', '=', context['force_company'])]
                location_ids = location_obj.search(cr, uid, domain, context=context)
            else:
                location_ids = context['location']
        else:
            if context.get('warehouse', False):
                wids = [context['warehouse']]
            else:
                wids = warehouse_obj.search(cr, uid, [], context=context)

            for w in warehouse_obj.browse(cr, uid, wids, context=context):
                location_ids.append(w.view_location_id.id)

        operator = context.get('compute_child', True) and 'child_of' or 'in'
        domain = context.get('force_company', False) and ['&', ('company_id', '=', context['force_company'])] or []
        return (
            domain + [('location_id', operator, location_ids)],
            domain + ['&', ('location_dest_id', operator, location_ids), '!', ('location_id', operator, location_ids)],
            domain + ['&', ('location_id', operator, location_ids), '!', ('location_dest_id', operator, location_ids)]
        )

    def _get_domain_dates(self, cr, uid, ids, context):
        from_date = context.get('from_date', False)
        to_date = context.get('to_date', False)
        domain = []
        if from_date:
            domain.append(('date', '>=', from_date))
        if to_date:
            domain.append(('date', '<=', to_date))
        return domain

    def _product_available(self, cr, uid, ids, field_names=None, arg=False, context=None):
        context = context or {}
        field_names = field_names or []

        domain_products = [('product_id', 'in', ids)]
        domain_quant, domain_move_in, domain_move_out = self._get_domain_locations(cr, uid, ids, context=context)
        domain_move_in += self._get_domain_dates(cr, uid, ids, context=context) + [('state', 'not in', ('done', 'cancel'))] + domain_products
        domain_move_out += self._get_domain_dates(cr, uid, ids, context=context) + [('state', 'not in', ('done', 'cancel'))] + domain_products
        domain_quant += domain_products
        if context.get('lot_id') or context.get('owner_id') or context.get('package_id'):
            if context.get('lot_id'):
                domain_quant.append(('lot_id', '=', context['lot_id']))
            if context.get('owner_id'):
                domain_quant.append(('owner_id', '=', context['owner_id']))
            if context.get('package_id'):
                domain_quant.append(('package_id', '=', context['package_id']))
            moves_in = []
            moves_out = []
        else:
            moves_in = self.pool.get('stock.move').read_group(cr, uid, domain_move_in, ['product_id', 'product_qty'], ['product_id'], context=context)
            moves_out = self.pool.get('stock.move').read_group(cr, uid, domain_move_out, ['product_id', 'product_qty'], ['product_id'], context=context)

        quants = self.pool.get('stock.quant').read_group(cr, uid, domain_quant, ['product_id', 'qty'], ['product_id'], context=context)
        quants = dict(map(lambda x: (x['product_id'][0], x['qty']), quants))

        moves_in = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_in))
        moves_out = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_out))
        res = {}
        for id in ids:
            print"====quants============",quants
            avail_quant=0.0
            avail_move_in=0.0
            avail_move_out=0.0
            if self.browse(cr,uid,id).child_ids:
                avail_quant=quants.get(id, 0.0)
                avail_move_in=moves_in.get(id, 0.0)
                avail_move_out=moves_out.get(id, 0.0)
                for child in self.browse(cr,uid,id).child_ids:
                    print'childdddddddddd',child.parent_coefficient,quants.get(child.id, 0.0)
                    print"====quants=======child*************=====",quants
                    domain_quant, domain_move_in, domain_move_out = self._get_domain_locations(cr, uid, [child.id], context=context)
                    quants = self.pool.get('stock.quant').read_group(cr, uid, domain_quant, ['product_id', 'qty'], ['product_id'], context=context)
                    quants = dict(map(lambda x: (x['product_id'][0], x['qty']), quants))
                    avail_quant = avail_quant + quants.get(child.id, 0.0)*child.parent_coefficient
                    print"====moves_in=======child*************=====",moves_in
                    moves_in = self.pool.get('stock.move').read_group(cr, uid, domain_move_in, ['product_id', 'product_qty'], ['product_id'], context=context)
                    moves_in = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_in))
                    avail_move_in = avail_move_in + moves_in.get(child.id, 0.0)*child.parent_coefficient
                    print"====moves_out=======child*************=====",moves_out
                    moves_out = self.pool.get('stock.move').read_group(cr, uid, domain_move_out, ['product_id', 'product_qty'], ['product_id'], context=context)
                    moves_out = dict(map(lambda x: (x['product_id'][0], x['product_qty']), moves_out))
                    avail_move_out = avail_move_out + moves_out.get(child.id, 0.0)*child.parent_coefficient
                res[id] = {
                'qty_available': avail_quant,
                'incoming_qty': avail_move_in,
                'outgoing_qty': avail_move_out,
                'virtual_available': avail_quant + avail_move_in - avail_move_out,
            }   
            else:
                    
                res[id] = {
                    'qty_available': quants.get(id, 0.0),
                    'incoming_qty': moves_in.get(id, 0.0),
                    'outgoing_qty': moves_out.get(id, 0.0),
                    'virtual_available': quants.get(id, 0.0) + moves_in.get(id, 0.0) - moves_out.get(id, 0.0),
                }

        return res

    def _search_product_quantity(self, cr, uid, obj, name, domain, context):
        res = []
        for field, operator, value in domain:
            #to prevent sql injections
            assert field in ('qty_available', 'virtual_available', 'incoming_qty', 'outgoing_qty'), 'Invalid domain left operand'
            assert operator in ('<', '>', '=', '<=', '>='), 'Invalid domain operator'
            assert isinstance(value, (float, int)), 'Invalid domain right operand'

            if operator == '=':
                operator = '=='

            product_ids = self.search(cr, uid, [], context=context)
            ids = []
            if product_ids:
                #TODO: use a query instead of this browse record which is probably making the too much requests, but don't forget
                #the context that can be set with a location, an owner...
                for element in self.browse(cr, uid, product_ids, context=context):
                    if eval(str(element[field]) + operator + str(value)):
                        ids.append(element.id)
            res.append(('id', 'in', ids))
        return res

    def _product_available_text(self, cr, uid, ids, field_names=None, arg=False, context=None):
        res = {}
        for product in self.browse(cr, uid, ids, context=context):
            res[product.id] = str(product.qty_available) +  _(" On Hand")
        return res

    _columns = {
                'active_flag':fields.boolean('Active Flag'),
                'additional_info':fields.char('Additional Info'),
                'mwi_db_id':fields.char('MWI DB ID'),
                'available_to_purchase_flag':fields.boolean('Available to purchase flag'),
                'backorder_flag':fields.boolean('BackOrder Flag'),
                'case_qty':fields.integer('Case Quantity'),
                'closeout_flag':fields.boolean('Close Out Flag'),
                'compendium_code':fields.char('Compendium Code'),
                'container_qty':fields.integer('Container Qty'),
                'convert_from_mwi':fields.char('Convert From MWI'),
                'cooler_item_flag':fields.boolean('Cooler Item Flag'),
                'deacontrolled_substance_code':fields.boolean('DEAControlled Substance Code'),
                'doses':fields.float('Doses', digits=(16,4)),
                'dropship_flag':fields.boolean('Drop Ship Flag'),
                'dropship_text':fields.char('Drop Ship Text'),
                'has_image':fields.boolean('Has Image'),
                'has_purchased':fields.boolean('Has Purchased'),
                'has_relationship':fields.boolean('Has Relationship'),
                'hazardous':fields.boolean('Hazardous'),
                'hazardous_text':fields.char('HazardousText'),
                'human_label_flag':fields.boolean('Human Label Flag'),
                'labelfee_flag':fields.boolean('Label Fee Flag'),
                'manufacturer':fields.char('Manufacturer'),
                'manufacturer_id':fields.char('Manufacturer ID'),
                'manu_minorder_fee':fields.integer('Manu Min Order Fee'),
                'manu_minorder_weight':fields.integer('Manu Min Order Weight'),
                'mfgproductcode':fields.char('Manufacturer ID'),
                'qtymultiplier':fields.integer(''),
                'rx_flag':fields.boolean('RX Flag'),
                'searchableflag':fields.boolean('Searchable Flag'),
                'searchterms':fields.char('SearchTerms'),
                'showpricingflag':fields.boolean('Show Pricing Flag'),
                'specialorderflag':fields.boolean('Special Order Flag'),
                'specialordertext':fields.boolean('Special Order Text'),
                'unit':fields.char('Unit'),
                'web_description':fields.char('Web Description'),
                'minqty':fields.integer('Min Qty'),
                'msdc_code':fields.char('MSDS Code'),
                'newproductflag':fields.boolean('New Product Flag'),
                'newproducttext':fields.char('New Product Text'),
                'nonreturnable':fields.boolean('Non Returnable'),
                'nonreturnable_text':fields.char('Non Returnable Text'),
                'product_code':fields.char('Product Code'),
                'productdimwgt':fields.integer('Product DimWgt'),
                'product_price':fields.char('Product Price'),
                
                'description':fields.char('Description'),
                'discontinued_flag':fields.boolean('Discontinued Flag'),
                'act_ingrediants':fields.char('ActIngrediants'),
                'parent_coefficient':fields.float('Parent Coefficient', digits=(16,4)),
                'parent_product_id':fields.many2one('product.product','Parent'),
                'child_ids':fields.one2many('product.product','parent_product_id','Childs'),
        'qty_available_text': fields.function(_product_available_text, type='char'),
        'qty_available': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Quantity On Hand',
            fnct_search=_search_product_quantity,
            help="Current quantity of products.\n"
                 "In a context with a single Stock Location, this includes "
                 "goods stored at this Location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods stored in the Stock Location of this Warehouse, or any "
                 "of its children.\n"
                 "stored in the Stock Location of the Warehouse of this Shop, "
                 "or any of its children.\n"
                 "Otherwise, this includes goods stored in any Stock Location "
                 "with 'internal' type."),
        'virtual_available': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Forecast Quantity',
            fnct_search=_search_product_quantity,
            help="Forecast quantity (computed as Quantity On Hand "
                 "- Outgoing + Incoming)\n"
                 "In a context with a single Stock Location, this includes "
                 "goods stored in this location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods stored in the Stock Location of this Warehouse, or any "
                 "of its children.\n"
                 "Otherwise, this includes goods stored in any Stock Location "
                 "with 'internal' type."),
        'incoming_qty': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Incoming',
            fnct_search=_search_product_quantity,
            help="Quantity of products that are planned to arrive.\n"
                 "In a context with a single Stock Location, this includes "
                 "goods arriving to this Location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods arriving to the Stock Location of this Warehouse, or "
                 "any of its children.\n"
                 "Otherwise, this includes goods arriving to any Stock "
                 "Location with 'internal' type."),
        'outgoing_qty': fields.function(_product_available, multi='qty_available',
            type='float', digits_compute=dp.get_precision('Product Unit of Measure'),
            string='Outgoing',
            fnct_search=_search_product_quantity,
            help="Quantity of products that are planned to leave.\n"
                 "In a context with a single Stock Location, this includes "
                 "goods leaving this Location, or any of its children.\n"
                 "In a context with a single Warehouse, this includes "
                 "goods leaving the Stock Location of this Warehouse, or "
                 "any of its children.\n"
                 "Otherwise, this includes goods leaving any Stock "
                 "Location with 'internal' type."),
    }
    
    
class product_supplierinfo(osv.osv):
    _inherit = "product.supplierinfo"
    _columns={
              'supplier_uom':fields.char('Supplier UOM'),
              }
        


