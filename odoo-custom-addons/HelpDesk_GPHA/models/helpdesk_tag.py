from odoo import models, fields


class HelpdeskTag(models.Model):

    _name        = 'helpdesk.tag'
    _description = 'Helpdesk Ticket Tag'
    _order       = 'name'

    name = fields.Char(
        string='Tag',
        required=True,
        translate=True,
    )

    color = fields.Integer(
        string='Colour index',
        default=0,
        # Odoo has a built-in colour picker widget that maps integers 0-11
        # to preset colours. Store the index here, render with
        # widget="color" in the form view later.
        # 0=no colour, 1=red, 2=orange, 3=yellow ... 10=purple, 11=teal
    )

    active = fields.Boolean(default=True)