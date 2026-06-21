{
    'name': 'GPHA Problem Logging',
    'version': '18.0.1.0.0',
    'summary': 'Lightweight problem logging & tracking for GPHA',
    'category': 'Services',
    'author': 'Apps Units ',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/problem_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/problem_logging_views.xml',
    ],
    'installable': True,
    'application': True,
    'sequence': 12,
}
