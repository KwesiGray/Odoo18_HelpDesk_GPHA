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
        related='category_id.ticket_type',
        # related= reads the ticket_type field from the linked category record.
        # When a user picks "IT Hardware" as category, ticket_type automatically
        # becomes 'it'. No second dropdown. No user effort.
        string='Type',
        store=True,
        # store=True writes it to the helpdesk_ticket table so you can
        # still filter and group by type in reports and list views.
        readonly=True,
        # readonly=True because the user should never set this directly —
        # it comes from the category.
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

    occurred_date = fields.Date(
        string='Date Occurred',
        compute='_compute_occurred_parts',
        store=True)
    occurred_time = fields.Char(
        string='Time Occurred',
        compute='_compute_occurred_parts',
        store=True)

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

    total_time_spent = fields.Float(
        string='Total time spent (hrs)',
        compute='_compute_total_time',
        store=True,
        digits=(10, 2),
    )

    log_count = fields.Integer(
        string='Log entries',
        compute='_compute_log_count',
    )

    # Store the actual moment the problem occurred.
    occurred_at = fields.Datetime(
        string='Date/Time Problem Occurred',
        tracking=True,
        default=fields.Datetime.now,
    )

    office = fields.Char(
        string='Office (Source)',
        tracking=True)

    # ══════════════════════════════════════════════════════════════════════
    # 9. COMPUTE METHODS
    # ══════════════════════════════════════════════════════════════════════

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


    @api.depends('log_ids')
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    @api.depends('log_ids.time_spent')
    def _compute_total_time(self):
        """
        @api.depends('log_ids.time_spent') — note the dot notation.
        This tells Odoo: "recalculate when ANY log entry's time_spent
        field changes on ANY log linked to this ticket."
        Dot notation through relational fields is one of Odoo's
        most powerful @api.depends features.
        """
        for rec in self:
            rec.total_time_spent = sum(rec.log_ids.mapped('time_spent'))
            # .mapped('time_spent') → returns a list of all time_spent
            # values across the entire log_ids recordset.
            # sum() adds them up. Clean, readable, and works on 0 records too.

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

    def _log_action(self, action_type, old_state=None, new_state=None, note=None):
        """
        Internal helper — creates a structured log entry.
        Called by every state transition method so log entries
        are created consistently without repeating code.

        This is a private method (prefix _) — not exposed in the UI.
        """
        self.env['helpdesk.ticket.log'].create({
            'ticket_id': self.id,
            'action_type': action_type,
            'old_state': old_state,
            'new_state': new_state,
            'note': note,
            'user_id': self.env.user.id,
            'logged_at': fields.Datetime.now(),
        })

    def action_view_logs(self):
        """Open log entries for this ticket in a list view."""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Logs — {self.name}',
            'res_model': 'helpdesk.ticket.log',
            'view_mode': 'tree,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'default_ticket_id': self.id},
        }
        # Returning a dict from a button method opens a new view.
        # domain= pre-filters to only this ticket's logs.
        # context= pre-fills ticket_id if the user creates a new log from there.



    def action_submit(self):
        """draft → Submitted"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(f'Ticket "{rec.name}" is not in draft state.')
            old = rec.state
            rec.state = 'submitted'
            rec._log_action('state_change', old_state=old, new_state='submitted')


    # def action_start(self):
    #     """Move ticket from draft → in_progress."""
    #     for rec in self:
    #         if rec.state != 'submitted':
    #             raise UserError(
    #                 f'Ticket "{rec.name}" is already submitted or beyond.'
    #             )
    #         rec.state = 'in_progress'

    def action_start(self):
        """Submitted → In Progress"""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(f'Ticket "{rec.name}" is not in Submitted state.')
            old = rec.state
            rec.state = 'in_progress'
            rec._log_action('state_change', old_state=old, new_state='in_progress')


    def action_pending(self):
        """In Progress → Pending"""
        for rec in self:
            if rec.state not in ('draft', 'in_progress'):
                raise UserError('Only Draft or In Progress tickets can be set to Pending.')
            old = rec.state
            rec.state = 'pending'
            rec._log_action('state_change', old_state=old, new_state='pending')


    def action_resolve(self):
        """Any open state → Resolved"""
        for rec in self:
            if rec.state == 'closed':
                raise UserError('A closed ticket cannot be resolved directly.')
            old = rec.state
            rec.write({
                'state': 'resolved',
                'date_resolved': fields.Datetime.now(),
            })
            rec._log_action(
                'resolution',
                old_state=old,
                new_state='resolved',
                note=f'Resolved by {rec.env.user.name}',
            )

    def action_close(self):
        """Resolved → Closed"""
        for rec in self:
            if rec.state != 'resolved':
                raise UserError('Only resolved tickets can be closed.')
            old = rec.state
            rec.state = 'closed'
            rec._log_action('state_change', old_state=old, new_state='closed')


    def action_reopen(self):
        """Resolved / Closed → In Progress"""
        for rec in self:
            if rec.state not in ('resolved', 'closed'):
                raise UserError('Only resolved or closed tickets can be reopened.')
            old = rec.state
            rec.write({'state': 'in_progress', 'date_resolved': False})
            rec._log_action('state_change', old_state=old, new_state='in_progress',
                            note='Ticket reopened')

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