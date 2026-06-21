from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class GphaProblem(models.Model):
    _name = 'gpha.problem'
    _description = 'Problem'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, id desc'

    name = fields.Char(string='Title', required=True, tracking=True)
    problem_id = fields.Char(string='Problem ID', readonly=True, copy=False, index=True)

    # Employee complaint text
    description = fields.Text(string='Complaint / Description', tracking=False)

    category = fields.Selection(
        [('it', 'IT'), ('hr', 'HR'), ('operations', 'Operations')],
        required=True,
        default='it',
        tracking=True,
    )

    priority = fields.Selection(
        [('0', 'Low'), ('1', 'Medium'), ('2', 'High')],
        default='1',
        required=True,
        tracking=True,
    )

    # Employee metadata
    location = fields.Char(string='Location', tracking=True)
    office = fields.Char(string='Office (Source)', tracking=True)
    complainer_name = fields.Char(string='Name of Complainer', tracking=True)

    # Store the actual moment the problem occurred.
    occurred_at = fields.Datetime(
        string='Date/Time Problem Occurred',
        tracking=True,
        default=fields.Datetime.now,
    )

    # Convenience fields (optional) for UI/search; derived from occurred_at.
    occurred_date = fields.Date(string='Date Occurred', compute='_compute_occurred_parts', store=True)
    occurred_time = fields.Char(string='Time Occurred', compute='_compute_occurred_parts', store=True)

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('in_progress', 'In Progress'),
            ('resolved', 'Resolved'),
            ('closed', 'Closed'),
        ],
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )

    reporter_id = fields.Many2one(
        'res.users',
        string='Reported By (User)',
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
        tracking=True,
    )

    department = fields.Char(string='Department', tracking=True)

    assignee_id = fields.Many2one('res.users', string='Assigned To', tracking=True)
    due_date = fields.Date(string='Due Date', tracking=True)

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'gpha_problem_ir_attachment_rel',
        'problem_id',
        'attachment_id',
        string='Attachments',
    )

    # Extra employee-required fields (as requested)
    complaint = fields.Text(
        string='Complaint',
        related='description',
        readonly=False,
        store=False,
    )

    complaint_office = fields.Char(
        string='Office',
        related='office',
        readonly=False,
        store=False,
    )

    complaint_date = fields.Date(
        string='Date',
        related='occurred_date',
        readonly=True,
        store=False,
    )

    complaint_time = fields.Char(
        string='Time',
        related='occurred_time',
        readonly=True,
        store=False,
    )

    complainer = fields.Char(
        string='Name of the Complainer',
        related='complainer_name',
        readonly=False,
        store=False,
    )

    @api.depends('occurred_at')
    def _compute_occurred_parts(self):
        for rec in self:
            if rec.occurred_at:
                rec.occurred_date = fields.Datetime.to_datetime(rec.occurred_at).date()
                # Use user's timezone for display-oriented time
                rec.occurred_time = fields.Datetime.context_timestamp(rec, rec.occurred_at).strftime('%H:%M')
            else:
                rec.occurred_date = False
                rec.occurred_time = False

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if not vals.get('problem_id'):
                vals['problem_id'] = seq.next_by_code('gpha.problem') or _('NEW')
            # If employee didn't type a name, default it from their user.
            if not vals.get('complainer_name') and vals.get('reporter_id'):
                user = self.env['res.users'].browse(vals['reporter_id'])
                vals['complainer_name'] = user.name
        records = super().create(vals_list)
        # subscribe reporter to chatter
        for rec in records:
            rec.message_subscribe(partner_ids=[rec.reporter_id.partner_id.id])
        return records

    def write(self, vals):
        # Prevent employee fields from being modified once submitted.
        employee_locked_fields = {
            'name',
            'description',
            'complaint',
            'category',
            'priority',
            'location',
            'office',
            'complaint_office',
            'complainer_name',
            'complainer',
            'occurred_at',
            'attachment_ids',
            'reporter_id',
        }
        if employee_locked_fields.intersection(vals.keys()):
            for rec in self:
                # Allow system administrators to update these fields regardless of state
                if rec.state != 'draft' and not self.env.user.has_group('base.group_system'):
                    raise AccessError(_(
                        'You can only edit the employee complaint fields while the problem is in Draft (New) state.'
                    ))

        # capture assignment change to notify assignee
        old_assignees = {rec.id: rec.assignee_id for rec in self}
        res = super().write(vals)
        if 'assignee_id' in vals:
            for rec in self:
                new_assignee = rec.assignee_id
                if new_assignee and old_assignees.get(rec.id) != new_assignee:
                    rec.message_subscribe(partner_ids=[new_assignee.partner_id.id])
                    rec.message_post(
                        body=_('Problem assigned to %s') % new_assignee.display_name,
                        partner_ids=[new_assignee.partner_id.id],
                        message_type='notification',
                        subtype_xmlid='mail.mt_comment',
                    )
        return res

    def action_set_state(self, draft_state):
        self.ensure_one()
        if draft_state not in dict(self._fields['state']._description_selection(self.env)):
            raise AccessError(_('Invalid state'))
        self.state = draft_state

    def action_submit(self):
        """Employee submits the complaint so support can start working on it."""
        self.write({'state': 'submitted'})

    def action_start(self):
        # Support starts work after submission
        self.write({'state': 'in_progress'})

    def action_resolve(self):
        self.write({'state': 'resolved'})

    def action_close(self):
        self.write({'state': 'closed'})
