from odoo import models, fields


class HelpdeskCategory(models.Model):


    _name        = 'helpdesk.category'
    _description = 'Helpdesk Problem Category'
    _order       = 'sequence, name'   # sort by sequence first, then alphabetically

    #Fields

    name = fields.Char(
        string='Category name',
        required=True,
        translate=True,    # allows translation into other languages if needed
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        # Odoo's list views can show a drag handle when this field exists.
        # Lower number = appears higher in the list.
    )

    ticket_type = fields.Selection(
        selection=[
            ('it',    'IT / Technical'),
            ('field', 'Field / Operational'),
            ('hr', 'HR OPERATIONS'),
            ('support', 'Support'),
            ('other', 'Other'),
        ],
        string='Type',
        required=True,
        # Lets managers pre-classify categories so users don't have to
        # think about which type a category belongs to.
    )

    description = fields.Text(
        string='Description',
        # Plain text note about when to use this category.
        # Visible to managers in the configuration screen.
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        # THIS IS AN ODOO CONVENTION — any model with an 'active' field
        # gets automatic archive/unarchive behaviour.
        # active=False records are hidden from all searches by default
        # but not deleted. Users can restore them via Filters > Archived.
    )

    # ── Computed: ticket count ─────────────────────────────────────────────
    ticket_count = fields.Integer(
        string='Tickets',
        compute='_compute_ticket_count',
        # store=False here — we always want a live count, not a cached one
    )

    def _compute_ticket_count(self):
        # search_count() runs a SELECT COUNT(*) — efficient, no data loaded
        for rec in self:
            rec.ticket_count = self.env['helpdesk.ticket'].search_count([
                ('category_id', '=', rec.id)
            ])