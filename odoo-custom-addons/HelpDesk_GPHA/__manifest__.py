{
    'name': 'Help Desk (GPHA)',
    'version': '18.0.1.0.0',
    'summary': 'Internal IT and field operations problem logging',
    'description': """ Log, track and resolve IT and field operational problems.
        Internal staff helpdesk with SLA tracking and activity logs.""",

    'category': 'Services',
    'author': 'Graham David (APPS UNIT) ',
    'website': 'https://www.graytechnologies.tech',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/helpdesk_security.xml',
        'security/ir.model.access.csv',
        'data/helpdesk_data.xml',
        'views/helpdesk_ticket.xml',
        'views/helpdesk_menu.xml',

    ],
    'installable': True,
    'application': True,
    'sequence': 1,
}
