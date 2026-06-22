from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta


class HelpdeskTicket(models.Model):

    _name        = 'helpdesk.ticket'
    _description = 'Helpdesk Problem Ticket'
    _order       = 'priority desc, create_date desc'
    _rec_name = 'name'
    # Odoo uses _rec_name when displaying this record as a label in
    # a Many2one dropdown on ANOTHER form. "name" is the default but
    # it's good practice to be explicit.

    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Subject',
        required=True,
        tracking=True,
        # tracking=True on name means any edit to the subject
        # posts "Subject changed from X to Y" in the chatter.
    )

    reference = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        # copy=False → when you duplicate a ticket this field resets to False
        # so the duplicate gets a fresh reference via _compute_reference.
        default='New',
    )

    description = fields.Html(
        string='Problem description',
        # Html gives users a rich text editor in the form view.
        # Stored as HTML in the database (text column).
        # Use widget="html" in the view (Odoo auto-applies this for Html fields).
    )

    reporter_id = fields.Many2one(
        comodel_name='res.users',
        string='Reported by',
        required=True,
        default=lambda self: self.env.user,
        # lambda self: self.env.user  → sets the current logged-in user
        # as the default reporter when a new ticket is created.
        # self.env.user is always available — it's the user making the request.
        tracking=True,
    )


    ticket_type = fields.Selection(
        selection=[
            ('it', 'IT / Technical'),
            ('field', 'Field / Operational'),
            ('hr', 'HR OPERATIONS'),
            ('support', 'Support'),
            ('other', 'Other'),
        ],
        string='Type',
        required=True,
        tracking=True,
    )

    category_id = fields.Many2one(
        comodel_name='helpdesk.category',
        string='Category',
        ondelete='set null',
        # ondelete='set null' → if a manager deletes the "IT Hardware"
        # category, existing tickets keep their data but category_id
        # becomes False. Safe for history preservation.
        tracking=True,
    )

    priority = fields.Selection(
        selection=[
            ('0', 'Low'),
            ('1', 'Medium'),
            ('2', 'High'),
            ('3', 'Critical'),
        ],
        string='Priority',
        default='0',
        tracking=True,
        # Stored as '0','1','2','3' in DB.
        # In the form view use widget="priority" to render star icons.
        # The _order above uses this to sort Critical tickets first.
    )

    tag_ids = fields.Many2many(
        comodel_name='helpdesk.tag',
        relation='helpdesk_ticket_tag_rel',
        # relation= names the pivot table Odoo creates in PostgreSQL.
        # If you omit this, Odoo auto-generates a name — but being
        # explicit avoids name collisions in complex modules.
        column1='ticket_id',
        column2='tag_id',
        string='Tags',
    )



    state = fields.Selection(
        selection=[
            ('draft',        'Draft'),
            ('submitted', 'Submitted'),
            ('in_progress', 'In Progress'),
            ('pending',     'Pending'),
            ('resolved',    'Resolved'),
            ('closed',      'Closed'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        # tracking=True here is especially valuable — every state
        # change posts a timestamped message in the chatter, giving
        # you a full audit trail automatically.
    )

    kanban_state = fields.Selection(
        selection=[
            ('normal',  'In Progress'),
            ('blocked', 'Blocked'),
            ('done',    'Ready to progress'),
        ],
        string='Kanban state',
        default='normal',
        # kanban_state is separate from state.
        # state = the stage in the pipeline
        # kanban_state = the agent's confidence about moving it forward
        # Use widget="state_selection" in the kanban view to render
        # the coloured circle (green/red/grey) indicator.
    )


    assigned_to = fields.Many2one(
        comodel_name='res.users',
        string='Assigned to',
        tracking=True,
        # When this changes the chatter shows exactly who it was
        # reassigned from and to — invaluable for audits.
    )



    date_resolved = fields.Datetime(
        string='Resolved on',
        readonly=True,
        # Set programmatically inside action_resolve().
        # readonly=True → users cannot manually edit this.
        # It only gets a value when the system resolves the ticket.
        tracking=True,
    )

    sla_deadline = fields.Datetime(
        # Service level agreement deadline
        string='SLA deadline',
        compute='_compute_sla_deadline',
        store=True,
        # store=True → written to the database so you can filter and
        # group tickets by SLA deadline in list/graph views.
        # Without store=True it would recalculate on every page load
        # but never be searchable.
        tracking=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # 8. COMPUTED FIELDS
    # ══════════════════════════════════════════════════════════════════════

    resolution_time = fields.Float(
        string='Resolution time (hrs)',
        compute='_compute_resolution_time',
        store=True,
        digits=(10, 2),
        # digits=(precision, scale) → 10 total digits, 2 decimal places
        # e.g. 47.50 hours stored as 47.50
    )

    is_overdue = fields.Boolean(
        string='Overdue',
        compute='_compute_is_overdue',
        store=True,
        # store=True allows a list view to show a red colour decorator
        # when is_overdue=True, and lets managers filter "all overdue tickets".
    )

    # One2many to the log model — built in step 1.5
    log_ids = fields.One2many(
        comodel_name='helpdesk.ticket.log',
        inverse_name='ticket_id',
        # inverse_name= the Many2one field on helpdesk.ticket.log
        # that points BACK to this ticket.
        string='Activity log',
    )

    # ══════════════════════════════════════════════════════════════════════
    # 9. COMPUTE METHODS
    # ══════════════════════════════════════════════════════════════════════

    @api.depends('create_date', 'priority')
    def _compute_sla_deadline(self):
        """
        SLA hours by priority:
            Critical → 4 hrs
            High     → 24 hrs
            Medium   → 48 hrs
            Low      → 72 hrs

        @api.depends('create_date', 'priority') tells Odoo:
        "Recalculate this field whenever create_date OR priority changes."
        Without @api.depends the field would never auto-update.
        """
        sla_hours = {'3': 4, '2': 24, '1': 48, '0': 72}
        for rec in self:
            if rec.create_date:
                hours = sla_hours.get(rec.priority, 72)
                rec.sla_deadline = rec.create_date + timedelta(hours=hours)
            else:
                rec.sla_deadline = False

    @api.depends('date_resolved', 'create_date')
    def _compute_resolution_time(self):
        """
        Calculates how many hours elapsed between creation and resolution.
        Only meaningful once date_resolved is set (i.e. ticket is resolved).
        """
        for rec in self:
            if rec.date_resolved and rec.create_date:
                delta = rec.date_resolved - rec.create_date
                rec.resolution_time = round(delta.total_seconds() / 3600, 2)
            else:
                rec.resolution_time = 0.0

    @api.depends('sla_deadline', 'state')
    def _compute_is_overdue(self):
        """
        A ticket is overdue when:
         - it has an SLA deadline, AND
         - the current time is past that deadline, AND
         - it's NOT yet resolved or closed.
        """
        now = fields.Datetime.now()
        for rec in self:
            rec.is_overdue = bool(
                rec.sla_deadline
                and now > rec.sla_deadline
                and rec.state not in ('resolved', 'closed')
            )

    # ══════════════════════════════════════════════════════════════════════
    # 10. AUTO REFERENCE GENERATION
    # ══════════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create() to auto-assign a sequential reference number.

        @api.model_create_multi is the Odoo 17+ way to override create —
        it receives a LIST of value dicts and must return a recordset.
        (Older tutorials show @api.model + single dict — that still works
        but model_create_multi is the correct pattern in Odoo 18.)

        self.env['ir.sequence'].next_by_code() pulls the next number from
        a named sequence. We'll define this sequence in helpdesk_data.xml.
        """
        for vals in vals_list:
            if vals.get('reference', 'New') == 'New':
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'helpdesk.ticket'
                ) or 'New'
        return super().create(vals_list)

    # ══════════════════════════════════════════════════════════════════════
    # 11. STATE TRANSITION METHODS (the state machine)
    # ══════════════════════════════════════════════════════════════════════

    def action_submit(self):
        """Move ticket from draft → submitted."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(
                    f'Ticket "{rec.name}" is already submitted or beyond.'
                )
            rec.state = 'submitted'

    def action_start(self):
        """Move ticket from draft → in_progress."""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(
                    f'Ticket "{rec.name}" is already submitted or beyond.'
                )
            rec.state = 'in_progress'

    def action_pending(self):
        """Move ticket to Pending — waiting on something external."""
        for rec in self:
            if rec.state not in ('draft', 'in_progress'):
                raise UserError('Only tickets in Draft or In Progress tickets can be set to Pending.')
            rec.state = 'pending'

    def action_resolve(self):
        """
        Resolve the ticket.
        Sets date_resolved which triggers _compute_resolution_time
        via @api.depends, automatically calculating resolution hours.
        """
        for rec in self:
            if rec.state == 'closed':
                raise UserError('A closed ticket cannot be resolved. Reopen it first.')
            rec.write({
                'state': 'resolved',
                'date_resolved': fields.Datetime.now(),
            })

    def action_close(self):
        """Close a resolved ticket. Resolved → Closed only."""
        for rec in self:
            if rec.state != 'resolved':
                raise UserError('Only resolved tickets can be closed.')
            rec.state = 'closed'

    def action_reopen(self):
        """Reopen a resolved or closed ticket back to In Progress."""
        for rec in self:
            if rec.state not in ('resolved', 'closed'):
                raise UserError('Only resolved or closed tickets can be reopened.')
            rec.write({
                'state': 'in_progress',
                'date_resolved': False,
                # Clear the resolved date — resolution clock resets
            })

    # ══════════════════════════════════════════════════════════════════════
    # 12. VALIDATION
    # ══════════════════════════════════════════════════════════════════════

    @api.constrains('assigned_to', 'state')
    def _check_assignment(self):
        """
        A ticket cannot move to In Progress without being assigned.
        @api.constrains fires after write/create — if it raises
        ValidationError the write is rolled back completely.
        """
        for rec in self:
            if rec.state == 'in_progress' and not rec.assigned_to:
                raise ValidationError(
                    f'Ticket "{rec.name}" must be assigned to someone before '
                    f'it can be set to In Progress.'
                )