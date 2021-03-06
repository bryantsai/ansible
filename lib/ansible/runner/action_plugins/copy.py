# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
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

import os

from ansible import utils
from ansible import errors
from ansible.runner.return_data import ReturnData

class ActionModule(object):

    def __init__(self, runner):
        self.runner = runner

    def run(self, conn, tmp, module_name, module_args, inject, complex_args=None, **kwargs):
        ''' handler for file transfer operations '''

        # load up options
        options = utils.parse_kv(module_args)
        source  = options.get('src', None)
        dest    = options.get('dest', None)

        if (source is None and not 'first_available_file' in inject) or dest is None:
            result=dict(failed=True, msg="src and dest are required")
            return ReturnData(conn=conn, result=result)

        # if we have first_available_file in our vars
        # look up the files and use the first one we find as src
        if 'first_available_file' in inject:
            found = False
            for fn in inject.get('first_available_file'):
                fn = utils.template(self.runner.basedir, fn, inject)
                fn = utils.path_dwim(self.runner.basedir, fn)
                if os.path.exists(fn):
                    source = fn
                    found = True
                    break
            if not found:
                results=dict(failed=True, msg="could not find src in first_available_file list")
                return ReturnData(conn=conn, result=results)
        else:
            source = utils.template(self.runner.basedir, source, inject)
            source = utils.path_dwim(self.runner.basedir, source)

        local_md5 = utils.md5(source)
        if local_md5 is None:
            result=dict(failed=True, msg="could not find src=%s" % source)
            return ReturnData(conn=conn, result=result)

        if dest.endswith("/"):
            base = os.path.basename(source)
            dest = os.path.join(dest, base)

        remote_md5 = self.runner._remote_md5(conn, tmp, dest)
        if remote_md5 == '3':
            # Destination is a directory
            dest = os.path.join(dest, os.path.basename(source))
            remote_md5 = self.runner._remote_md5(conn, tmp, dest)

        exec_rc = None
        if local_md5 != remote_md5:

            if self.runner.check:
                # TODO: if the filesize is small, include a nice pretty-printed diff by 
                # calling a (new) diff callback
                return ReturnData(conn=conn, result=dict(changed=True))

            # transfer the file to a remote tmp location
            tmp_src = tmp + os.path.basename(source)
            conn.put_file(source, tmp_src)
            # fix file permissions when the copy is done as a different user
            if self.runner.sudo and self.runner.sudo_user != 'root':
                self.runner._low_level_exec_command(conn, "chmod a+r %s" % tmp_src, tmp)

            # run the copy module
            module_args = "%s src=%s" % (module_args, tmp_src)
            return self.runner._execute_module(conn, tmp, 'copy', module_args, inject=inject)

        else:
            # no need to transfer the file, already correct md5, but still need to call
            # the file module in case we want to change attributes

            tmp_src = tmp + os.path.basename(source)
            module_args = "%s src=%s" % (module_args, tmp_src)
            if self.runner.check:
                module_args = "%s CHECKMODE=True" % module_args
            return self.runner._execute_module(conn, tmp, 'file', module_args, inject=inject)

