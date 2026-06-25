from odoo import models, fields


class HelpdeskOfficeLocation(models.Model):
    _name = 'helpdesk.office.location'
    _description = 'Helpdesk Office Location'
    _order = 'sequence, name_office'
    _rec_name = 'name_office'

    location = fields.Selection(
        selection=[
            ('head_office', 'Head Office'),
            ('Hospital', 'Hospital'),
            ('diagnostic', 'Diagnostic Center'),
            ('port', 'Port Environment'),
            ('dry bulk', 'Dry Bulk'),
            ('other', 'Other'),
        ],
        string='Location',
        required=True,
    )

    name_office = fields.Char(
        string='Office Location',
        required=True,
        translate=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    description = fields.Text(
        string='Description',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

