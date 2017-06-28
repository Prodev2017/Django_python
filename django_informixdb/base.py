"""
informix database backend for Django.

Requires informixdb
"""
import os
import sys
import platform

from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.validation import BaseDatabaseValidation
from django.core.exceptions import ImproperlyConfigured

from django.utils.six import binary_type, text_type
from django.utils.encoding import smart_str

from .client import DatabaseClient
from .creation import DatabaseCreation
from .introspection import DatabaseIntrospection
from .operations import DatabaseOperations
from .features import DatabaseFeatures
from .schema import DatabaseSchemaEditor

try:
    import pyodbc
except ImportError as e:
    e = sys.exc_info()[1]
    raise ImproperlyConfigured("Error loading pyodbc module:{}".format(e))


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'informixdb'
    Database = pyodbc

    DRIVER_MAP = {
        'DARWIN': '/Applications/IBM/informix/lib/cli/iclit09b.dylib',
        'LINUX': '/opt/IBM/informix/lib/cli/iclit09b.so',
    }

    data_types = {
        'AutoField': 'serial',
        'BigAutoField': 'bigserial',
        'BinaryField': 'blob',
        'BooleanField': 'boolean',
        'CharField': 'lvarchar(%(max_length)s)',
        'CommaSeparatedIntegerField': 'lvarchar(%(max_length)s)',
        'DateField': 'date',
        'DateTimeField': 'datetime year to fraction(5)',
        'DecimalField': 'decimal',
        'DurationField': 'interval',
        'FileField': 'lvarchar(%(max_length)s)',
        'FilePathField': 'lvarchar(%(max_length)s)',
        'FloatField': 'smallfloat',
        'IntegerField': 'integer',
        'BigIntegerField': 'bigint',
        'IPAddressField': 'char(15)',
        'GenericIPAddressField': 'char(39)',
        'NullBooleanField': 'boolean',
        'OneToOneField': 'integer',
        'PositiveIntegerField': 'integer',
        'PositiveSmallIntegerField': 'smallint',
        'SlugField': 'lvarchar(%(max_length)s)',
        'SmallIntegerField': 'smallint',
        'TextField': 'text',
        'TimeField': 'datetime hour to second',
        'UUIDField': 'char(32)',
    }

    data_type_check_constraints = {
        'PositiveIntegerField': '%(column)s >= 0',
        'PositiveSmallIntegerField': '%(column)s >= 0',
    }

    operators = {
        'exact': '= %s',
        'iexact': "= LOWER(%s)",
        'contains': "LIKE %s ESCAPE '\\'",
        'icontains': "LIKE LOWER(%s) ESCAPE '\\'",
        'gt': '> %s',
        'gte': '>= %s',
        'lt': '< %s',
        'lte': '<= %s',
        'startswith': "LIKE %s ESCAPE '\\'",
        'endswith': "LIKE %s ESCAPE '\\'",
        'istartswith': "LIKE LOWER(%s) ESCAPE '\\'",
        'iendswith': "LIKE LOWER(%s) ESCAPE '\\'",
        'regex': 'LIKE %s',
        'iregex': 'LIKE %s',
    }

    # The patterns below are used to generate SQL pattern lookup clauses when
    # the right-hand side of the lookup isn't a raw string (it might be an expression
    # or the result of a bilateral transformation).
    # In those cases, special characters for LIKE operators (e.g. \, *, _) should be
    # escaped on database side.
    #
    # Note: we use str.format() here for readability as '%' is used as a wildcard for
    # the LIKE operator.
    pattern_esc = r"REPLACE(REPLACE(REPLACE({}, '\', '\\'), '%%', '\%%'), '_', '\_')"
    pattern_ops = {
        'contains': "LIKE '%%' ESCAPE '\\' || {} || '%%'",
        'icontains': "LIKE '%%' ESCAPE '\\' || UPPER({}) || '%%'",
        'startswith': "LIKE {} ESCAPE '\\' || '%%'",
        'istartswith': "LIKE UPPER({}) ESCAPE '\\' || '%%'",
        'endswith': "LIKE '%%' ESCAPE '\\' || {}",
        'iendswith': "LIKE '%%' ESCAPE '\\' || UPPER({})",
    }
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations
    SchemaEditorClass = DatabaseSchemaEditor
    validation_class = BaseDatabaseValidation

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)
        options = self.settings_dict.get('OPTIONS', None)
        if options:
            self.encoding = options.get('encoding', 'utf-8')
            # make lookup operators to be collation-sensitive if needed
            self.collation = options.get('collation', None)
            if self.collation:
                self.operators = dict(self.__class__.operators)
                ops = {}
                for op in self.operators:
                    sql = self.operators[op]
                    if sql.startswith('LIKE '):
                        ops[op] = '%s COLLATE %s' % (sql, self.collation)
                self.operators.update(ops)

        self.features = self.features_class(self)
        self.ops = self.ops_class(self)
        self.client = self.client_class(self)
        self.creation = self.creation_class(self)
        self.introspection = self.introspection_class(self)
        self.validation = self.validation_class(self)

    def get_driver_path(self):
        system = platform.system().upper()
        try:
            return self.DRIVER_MAP[system]
        except KeyError:
            raise ImproperlyConfigured('cannot locate informix driver, please specify')

    def get_connection_params(self):
        settings = self.settings_dict

        if 'DSN' not in settings:
            for k in ['NAME', 'SERVER', 'USER', 'PASSWORD']:
                if k not in settings:
                    raise ImproperlyConfigured('{} is a required setting for an informix connection'.format(k))
        conn_params = settings.copy()

        # Ensure the driver is set in the options
        options = conn_params.get('OPTIONS', {})
        if 'DRIVER' not in options:
            options['DRIVER'] = self.get_driver_path()
        if not os.path.exists(options['DRIVER']):
            raise ImproperlyConfigured('cannot find Informix driver at {}'.format(options['DRIVER']))
        conn_params['OPTIONS'] = options

        conn_params['AUTOCOMMIT'] = False if 'AUTOCOMMIT' not in conn_params else conn_params['AUTOCOMMIT']

        return conn_params

    def _handle_constraint(self, raw_data):
        """
        PyODBC will not handle a -101 type which is a informix constraint
        This is a simple unpacking of a bytes type.
        _idx: constraint id
        _idtype: constraint type
        """
        return raw_data.decode('utf8')

    def get_new_connection(self, conn_params):
        parts = [
            'Driver={{{}}}'.format(conn_params['OPTIONS']['DRIVER']),
        ]

        if 'DSN' in conn_params:
            parts.append('DSN={}'.format(conn_params['DSN']))
        if 'SERVER' in conn_params:
            parts.append('Server={}'.format(conn_params['SERVER']))
        if 'NAME' in conn_params and conn_params['NAME'] is not None:
            parts.append('Database={}'.format(conn_params['NAME']))
        elif conn_params['NAME'] is None:
            parts.append('CONNECTDATABASE=no')
        if 'USER' in conn_params:
            parts.append('Uid={}'.format(conn_params['USER']))
        if 'PASSWORD' in conn_params:
            parts.append('Pwd={}'.format(conn_params['PASSWORD']))
        if 'CPTIMEOUT' in conn_params['OPTIONS']:
            parts.append('CPTimeout={}'.format(conn_params['OPTIONS']['CPTIMEOUT']))

        connection_string = ';'.join(parts)
        self.connection = pyodbc.connect(connection_string, autocommit=conn_params['AUTOCOMMIT'])

        self.connection.setdecoding(pyodbc.SQL_WCHAR, encoding='UTF-8')
        self.connection.setdecoding(pyodbc.SQL_CHAR, encoding='UTF-8')
        self.connection.setdecoding(pyodbc.SQL_WMETADATA, encoding='UTF-8')
        self.connection.setencoding(encoding='UTF-8')

        self.connection.add_output_converter(-101, self._handle_constraint)

        return self.connection

    def init_connection_state(self):
        pass

    def create_cursor(self, name=None):
        return CursorWrapper(self.connection.cursor(), self)

    def _set_autocommit(self, autocommit):
        with self.wrap_database_errors:
            self.connection.autocommit = autocommit

    def check_constraints(self, table_names=None):
        """
        To check constraints, we set constraints to immediate. Then, when, we're done we must ensure they
        are returned to deferred.
        """
        self.cursor().execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.cursor().execute('SET CONSTRAINTS ALL DEFERRED')

    def _start_transaction_under_autocommit(self):
        """
        Start a transaction explicitly in autocommit mode.
        """
        start_sql = self.ops.start_transaction_sql()
        self.cursor().execute(start_sql)

    def is_usable(self):
        try:
            # Use a cursor directly, bypassing Django's utilities.
            self.connection.cursor().execute("SELECT 1")
        except pyodbc.Error:
            return False
        else:
            return True

    def read_dirty(self):
        self.cursor().execute('set isolation to dirty read;')

    def read_committed(self):
        self.cursor().execute('set isolation to committed read;')

    def _commit(self):
        if self.connection is not None:
            with self.wrap_database_errors:
                return self.cursor().execute("COMMIT WORK")

    def _rollback(self):
        if self.connection is not None:
            with self.wrap_database_errors:
                return self.cursor().execute("ROLLBACK WORK")


class CursorWrapper(object):
    """
    A wrapper around the pyodbc's cursor that takes in account a) some pyodbc
    DB-API 2.0 implementation and b) some common ODBC driver particularities.
    """
    def __init__(self, cursor, connection):
        self.active = True
        self.cursor = cursor
        self.connection = connection
        self.driver_charset = False  # connection.driver_charset
        self.last_sql = ''
        self.last_params = ()

    def close(self):
        if self.active:
            self.active = False
            self.cursor.close()

    def format_sql(self, sql, params):
        if isinstance(sql, text_type):
            # FreeTDS (and other ODBC drivers?) doesn't support Unicode
            # yet, so we need to encode the SQL clause itself in utf-8
            sql = smart_str(sql, self.driver_charset)

        # pyodbc uses '?' instead of '%s' as parameter placeholder.
        if params is not None:
            pass
            # sql = sql % tuple('?' * len(params))

        return sql

    def format_params(self, params):
        fp = []
        if params is not None:
            for p in params:
                if isinstance(p, text_type):
                    if self.driver_charset:
                        # FreeTDS (and other ODBC drivers?) doesn't support Unicode
                        # yet, so we need to encode parameters in utf-8
                        fp.append(smart_str(p, self.driver_charset))
                    else:
                        fp.append(p)

                elif isinstance(p, binary_type):
                    fp.append(p)

                elif isinstance(p, type(True)):
                    if p:
                        fp.append(1)
                    else:
                        fp.append(0)

                else:
                    fp.append(p)

        return tuple(fp)

    def execute(self, sql, params=None):
        self.last_sql = sql
        sql = self.format_sql(sql, params)
        params = self.format_params(params)
        self.last_params = params
        return self.cursor.execute(sql, params)

    def executemany(self, sql, params_list=()):
        if not params_list:
            return None
        raw_pll = [p for p in params_list]
        sql = self.format_sql(sql, raw_pll[0])
        params_list = [self.format_params(p) for p in raw_pll]
        return self.cursor.executemany(sql, params_list)

    def format_rows(self, rows):
        return list(map(self.format_row, rows))

    def format_row(self, row):
        """
        Decode data coming from the database if needed and convert rows to tuples
        (pyodbc Rows are not sliceable).
        """
        if self.driver_charset:
            for i in range(len(row)):
                f = row[i]
                # FreeTDS (and other ODBC drivers?) doesn't support Unicode
                # yet, so we need to decode utf-8 data coming from the DB
                if isinstance(f, binary_type):
                    row[i] = f.decode(self.driver_charset)
        return row

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is not None:
            row = self.format_row(row)
        # Any remaining rows in the current set must be discarded
        # before changing autocommit mode when you use FreeTDS
        self.cursor.nextset()
        return row

    def fetchmany(self, chunk):
        return self.format_rows(self.cursor.fetchmany(chunk))

    def fetchall(self):
        return self.format_rows(self.cursor.fetchall())

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return self.__dict__[attr]
        return getattr(self.cursor, attr)

    def __iter__(self):
        return iter(self.cursor)
