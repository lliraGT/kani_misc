# -*- coding: utf-8 -*-

from odoo import models, fields, api, _ # type: ignore
from math import ceil
from odoo.exceptions import UserError # type: ignore
import json


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    
    is_special_product = fields.Boolean(
        string='Is Special Product',
        compute='_compute_is_special_product',
        store=True,
        help='Indicates if this production is for the special product that requires fixed batch splitting'
    )
    
    @api.depends('product_id')
    def _compute_is_special_product(self):
        target_product_id = 5236  # "Tortas Pollo LifeStyle - Suscripción"
        for record in self:
            if record.product_id and record.product_id.product_tmpl_id.id == target_product_id:
                record.is_special_product = True
            else:
                record.is_special_product = False
    
    def action_auto_split_fixed_batches(self):
        """Custom action to split into fixed batch quantities"""
        self.ensure_one()
        
        if not self.is_special_product:
            raise UserError(_("This action can only be used with the special product 'Tortas Pollo LifeStyle - Suscripción'"))
        
        # Minimum number of batches
        min_batches = 5
        # Fixed quantity per batch
        fixed_qty_per_batch = 41.0
        
        # Calculate how many batches we need to cover the total quantity
        # (at least 5 batches, and at least enough to cover the total quantity with 41 units per batch)
        required_batches = ceil(self.product_qty / fixed_qty_per_batch)
        batches_needed = max(min_batches, required_batches)
        
        # Prepare the split quantities (all equal to fixed_qty_per_batch)
        split_quantities = [fixed_qty_per_batch] * batches_needed
        
        # Calculate the total that will be produced
        total_to_produce = sum(split_quantities)
        
        # Check if we'll overproduce and warn the user
        if total_to_produce > self.product_qty:
            return {
                'name': _('Overproduction Warning'),
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.auto.split.confirm',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_production_id': self.id,
                    'default_original_qty': self.product_qty,
                    'default_future_qty': total_to_produce,
                    'default_split_quantities': json.dumps(split_quantities),
                }
            }
        
        # If no overproduction, directly perform the split
        return self._perform_fixed_split(split_quantities)
    
    def _perform_fixed_split(self, split_quantities):
        """Split the production order into the specified quantities"""
        self.ensure_one()
        
        # We'll create the new productions manually
        new_production_ids = []
        main_production = self
        
        # Create production orders for all quantities except the last one
        for i, qty in enumerate(split_quantities[:-1]):
            # Copy the original production
            new_production = main_production.copy({
                'product_qty': qty,
                'name': f"{main_production.name}.{i+1}",
            })
            
            # Add to our list of new productions
            new_production_ids.append(new_production.id)
            
        # Update the original production with the last quantity
        main_production.write({
            'product_qty': split_quantities[-1],
            'name': f"{main_production.name}.{len(split_quantities)}",
        })
        
        # Add the main production to the list of productions
        new_production_ids.append(main_production.id)
        
        # Return an action to show the split productions
        return {
            'name': _('Split Productions'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', new_production_ids)],
            'target': 'current',
        }


class MrpAutoSplitConfirm(models.TransientModel):
    _name = 'mrp.auto.split.confirm'
    _description = 'Confirm Production Auto Split with Overproduction'
    
    production_id = fields.Many2one('mrp.production', string='Production Order', required=True)
    original_qty = fields.Float(string='Original Quantity')
    future_qty = fields.Float(string='Future Quantity')
    split_quantities = fields.Char(string='Split Quantities')
    
    def action_confirm_split(self):
        """Confirm the split operation despite overproduction"""
        self.ensure_one()
        
        # Parse the split quantities from the string representation
        split_quantities = json.loads(self.split_quantities)
        
        # Perform the split
        return self.production_id._perform_fixed_split(split_quantities)
    
    def action_cancel(self):
        """Cancel the split operation"""
        return {'type': 'ir.actions.act_window_close'}