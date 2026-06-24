from odoo import models, fields, api


class HelpdeskTicketLog(models.Model):

    _name        = 'helpdesk.ticket.log'
    _description = 'Helpdesk Ticket Activity Log'
    _order       = 'logged_at desc'

    # ══════════════════════════════════════════════════════════════════════
    # 2. THE CRITICAL FIELD — the foreign key back to the ticket
    # ══════════════════════════════════════════════════════════════════════
    ticket_id = fields.Many2one(
        comodel_name='helpdesk.ticket',
        string='Ticket',
        required=True,
        ondelete='cascade',
        # ondelete='cascade' → if the parent ticket is deleted,
        # ALL its log entries are deleted too.
        # This is correct for child records that have no meaning
        # without their parent. Compare to category_id on the ticket
        # which uses 'set null' — categories can exist independently.
        index=True,
        # index=True → adds a PostgreSQL index on this column.
        # Since we constantly query "give me all logs for ticket X",
        # an index makes that lookup fast even with thousands of records.
    )

    # ══════════════════════════════════════════════════════════════════════
    # 3. WHAT HAPPENED
    # ══════════════════════════════════════════════════════════════════════
    action_type = fields.Selection(
        selection=[
            ('state_change',  'State change'),
            ('assignment',    'Assignment change'),
            ('note',          'Note added'),
            ('time_log',      'Time logged'),
            ('escalation',    'Escalated'),
            ('resolution',    'Resolution'),
        ],
        string='Action',
        required=True,
        default='note',
        # Having a typed action_type means you can later run queries like:
        # "show me all escalations this month" or
        # "how many state changes did ticket #42 go through"
    )

    old_state = fields.Selection(
        selection=[
            ('draft',         'Draft'),
            ('submitted',      'Submitted'),
            ('in_progress', 'In Progress'),
            ('pending',     'Pending'),
            ('resolved',    'Resolved'),
            ('closed',      'Closed'),
        ],
        string='From state',
        # Snapshot of the state BEFORE the action.
        # Populated by action_type='state_change' entries.
    )

    new_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('in_progress', 'In Progress'),
            ('pending',     'Pending'),
            ('resolved',    'Resolved'),
            ('closed',      'Closed'),
        ],
        string='To state',
        # Snapshot of the state AFTER the action.
    )

    note = fields.Text(
        string='Note',
        # Plain text — keep this Text not Html.
        # Log entries are system records, not rich documents.
        # Keeps the table clean and queryable.
    )

    # ══════════════════════════════════════════════════════════════════════
    # 4. WHO DID IT & WHEN
    # ══════════════════════════════════════════════════════════════════════
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='By',
        required=True,
        default=lambda self: self.env.user,
        ondelete='restrict',
        # Don't cascade-delete logs if a user account is removed.
        # The historical record should survive staff changes.
    )

    logged_at = fields.Datetime(
        string='Logged at',
        required=True,
        default=fields.Datetime.now,
        # Note: fields.Datetime.now (no parentheses) is passed as a
        # callable default — Odoo calls it at record creation time.
        # fields.Datetime.now() WITH parentheses would evaluate once
        # at class definition time — same timestamp for every record!
        # This is a common beginner mistake.
    )

    # ══════════════════════════════════════════════════════════════════════
    # 5. TIME TRACKING
    # ══════════════════════════════════════════════════════════════════════
    time_spent = fields.Float(
        string='Time spent (hrs)',
        digits=(10, 2),
        default=0.0,
        # Optional — staff log how long they spent on this action.
        # You can sum these across a ticket's log_ids to get total effort.
    )

    # ══════════════════════════════════════════════════════════════════════
    # 6. COMPUTED: total time on the ticket (convenience field)
    # ══════════════════════════════════════════════════════════════════════
    # NOTE: This is defined on the TICKET model (helpdesk.ticket),
    # not here — see the addition below that you need to add to
    # helpdesk_ticket.py.

    # ══════════════════════════════════════════════════════════════════════
    # 7. HOOKS: CREATE & WRITE to update parent ticket's total_time_spent
    # ══════════════════════════════════════════════════════════════════════
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to:
        1. Ensure logged_at is always set even if not supplied.
        2. After creating logs, immediately recompute parent ticket's total_time_spent

        This ensures that total_time_spent updates IMMEDIATELY instead of waiting
        for the next page load or explicit access to the field.
        """
        for vals in vals_list:
            if not vals.get('logged_at'):
                vals['logged_at'] = fields.Datetime.now()

        # Call parent create
        records = super().create(vals_list)

        # Collect all parent tickets affected by these new logs
        parent_tickets = records.mapped('ticket_id')
        if parent_tickets:
            # Force recompute of total_time_spent on all affected tickets
            parent_tickets._compute_total_time()

        return records

    def write(self, vals):
        """
        Override write to:
        1. Perform normal write operation.
        2. If time_spent is being changed, immediately recompute parent ticket's total_time_spent

        This ensures that when a user edits an existing time log entry,
        the parent ticket's total updates right away.
        """
        # Capture parent tickets BEFORE the write — this handles cases
        # where ticket_id is being moved from one ticket to another.
        old_parent_tickets = self.mapped('ticket_id')

        # Perform the write
        result = super().write(vals)

        # After write, collect the (possibly new) parent tickets
        new_parent_tickets = self.mapped('ticket_id')

        # Decide whether we need to recompute: if time_spent changed, or
        # ticket_id changed (so logs moved between tickets), recompute both
        # the old and new parent tickets to keep totals correct.
        needs_recompute = False
        if 'time_spent' in vals:
            needs_recompute = True
        if 'ticket_id' in vals:
            needs_recompute = True

        if needs_recompute:
            # union of old and new
            affected = (old_parent_tickets | new_parent_tickets)
            if affected:
                affected._compute_total_time()

        return result

    def unlink(self):
        """
        Override unlink so that when logs are deleted we recompute the
        total_time_spent on their parent tickets.
        """
        parent_tickets = self.mapped('ticket_id')
        result = super().unlink()
        if parent_tickets:
            parent_tickets._compute_total_time()

        return result
