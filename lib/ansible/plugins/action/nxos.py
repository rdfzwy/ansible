#
# (c) 2016 Red Hat Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import sys
import copy

from ansible import constants as C
from ansible.module_utils._text import to_text
from ansible.module_utils.connection import Connection
from ansible.plugins.action.normal import ActionModule as _ActionModule
from ansible.module_utils.network_common import load_provider
from ansible.module_utils.nxos import nxos_provider_spec

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()


class ActionModule(_ActionModule):

    def run(self, tmp=None, task_vars=None):
        socket_path = None

        if self._play_context.connection == 'network_cli':
            provider = self._task.args.get('provider', {})
            if any(provider.values()):
                display.warning('provider is unnecessary when using network_cli and will be ignored')
        elif self._play_context.connection == 'local':
            provider = load_provider(nxos_provider_spec, self._task.args)
            transport = provider['transport'] or 'cli'

            display.vvvv('connection transport is %s' % transport, self._play_context.remote_addr)

            if transport == 'cli':
                pc = copy.deepcopy(self._play_context)
                pc.connection = 'network_cli'
                pc.network_os = 'nxos'
                pc.remote_addr = provider['host'] or self._play_context.remote_addr
                pc.port = int(provider['port'] or self._play_context.port or 22)
                pc.remote_user = provider['username'] or self._play_context.connection_user
                pc.password = provider['password'] or self._play_context.password
                pc.private_key_file = provider['ssh_keyfile'] or self._play_context.private_key_file
                pc.timeout = int(provider['timeout'] or C.PERSISTENT_COMMAND_TIMEOUT)

                display.vvv('using connection plugin %s' % pc.connection, pc.remote_addr)
                connection = self._shared_loader_obj.connection_loader.get('persistent', pc, sys.stdin)

                socket_path = connection.run()
                display.vvvv('socket_path: %s' % socket_path, pc.remote_addr)
                if not socket_path:
                    return {'failed': True,
                            'msg': 'unable to open shell. Please see: ' +
                                   'https://docs.ansible.com/ansible/network_debug_troubleshooting.html#unable-to-open-shell'}

                task_vars['ansible_socket'] = socket_path

        else:
            provider['transport'] = 'nxapi'
            if provider.get('host') is None:
                provider['host'] = self._play_context.remote_addr

            if provider.get('port') is None:
                if provider.get('use_ssl'):
                    provider['port'] = 443
                else:
                    provider['port'] = 80

            if provider.get('timeout') is None:
                provider['timeout'] = C.PERSISTENT_COMMAND_TIMEOUT

            if provider.get('username') is None:
                provider['username'] = self._play_context.connection_user

            if provider.get('password') is None:
                provider['password'] = self._play_context.password

            if provider.get('use_ssl') is None:
                provider['use_ssl'] = False

            if provider.get('validate_certs') is None:
                provider['validate_certs'] = True

            self._task.args['provider'] = provider

        if (self._play_context.connection == 'local' and transport == 'cli') or self._play_context.connection == 'network_cli':
            # make sure we are in the right cli context which should be
            # enable mode and not config module
            if socket_path is None:
                socket_path = self._connection.socket_path

            conn = Connection(socket_path)
            out = conn.get_prompt()
            while to_text(out, errors='surrogate_then_replace').strip().endswith(')#'):
                display.vvvv('wrong context, sending exit to device', self._play_context.remote_addr)
                conn.send_command('exit')
                out = conn.get_prompt()

        result = super(ActionModule, self).run(tmp, task_vars)
        return result
