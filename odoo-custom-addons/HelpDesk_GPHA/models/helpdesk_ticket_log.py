from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta


class HelpdeskTicketLog(models.Model):

    _name = 'helpdesk.ticket.log'
    _description = 'Helpdesk Ticket Log'

    ticket_id = fields.Many2one(
        comodel_name='helpdesk.ticket',
        string='Ticket',
        ondelete='cascade',
        required=True,
    )

    author_id = fields.Many2one(
        comodel_name='res.users',
        string='Author',
        default=lambda self: self.env.user,
        readonly=True,
    )

    note = fields.Text(string='Note')
    create_date = fields.Datetime(string='Created on', readonly=True)
