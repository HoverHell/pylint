"""Unit tests for the pylint checkers in :mod:`pylint.extensions.check_docs`,
in particular the parameter documentation checker `DocstringChecker`
"""
from __future__ import division, print_function, absolute_import

import unittest
import sys

import astroid
from astroid import test_utils
from pylint.testutils import CheckerTestCase, Message, set_config

import pylint.extensions._check_docs_utils as utils


from astroid import decorators

@decorators.raise_if_nothing_inferred
def unpack_infer(stmt, context=None):
    """recursively generate nodes inferred by the given statement.
    If the inferred value is a list or a tuple, recurse on the elements
    """
    print("trying to infer", stmt)
    if isinstance(stmt, (astroid.List, astroid.Tuple)):
        for elt in stmt.elts:
            if elt is astroid.Uninferable:
                yield elt
                continue
            for inferred_elt in unpack_infer(elt, context):
                yield inferred_elt
        # Explicit StopIteration to return error information, see comment
        # in raise_if_nothing_inferred.
        raise StopIteration(dict(node=stmt, context=context))
    # if inferred is a final node, return it and stop
    inferred = next(stmt.infer(context))
    print("I inferred this for node", inferred, stmt)
    if inferred is stmt:
        yield inferred
        # Explicit StopIteration to return error information, see comment
        # in raise_if_nothing_inferred.
        raise StopIteration(dict(node=stmt, context=context))
    # else, infer recursivly, except Uninferable object that should be returned as is
    print("inferring again everything for", stmt)
    for inferred in stmt.infer(context):
        if inferred is astroid.Uninferable:
            yield inferred
        else:
            for inf_inf in unpack_infer(inferred, context):
                yield inf_inf
    raise StopIteration(dict(node=stmt, context=context))

def possible_exc_types(node):
    """
    Gets all of the possible raised exception types for the given raise node.

    .. note::

        Caught exception types are ignored.


    :param node: The raise node to find exception types for.

    :returns: A list of exception types possibly raised by :param:`node`.
    :rtype: list(str)
    """
    excs = []
    if isinstance(node.exc, astroid.Name):
        excs = [node.exc.name]
    elif (isinstance(node.exc, astroid.Call) and
          isinstance(node.exc.func, astroid.Name)):
        excs = [node.exc.func.name]
    elif node.exc is None:
        print("----> looking for node", node, node.exc)
        handler = node.parent
        while handler and not isinstance(handler, astroid.ExceptHandler):
            handler = handler.parent

        if handler and handler.type:
            print("----> found handler", handler, handler.type)
            print("KeyError mro", KeyError.__mro__)
            print("ValueError mro", ValueError.__mro__)
            excs = (exc.name for exc in unpack_infer(handler.type))

    excs = set(exc for exc in excs if not utils.node_ignores_exception(node, exc))
    return excs


class SpaceIndentationTest(unittest.TestCase):
    """Tests for pylint_plugin.ParamDocChecker"""

    def test_space_indentation(self):
        self.assertEqual(utils.space_indentation('abc'), 0)
        self.assertEqual(utils.space_indentation(''), 0)
        self.assertEqual(utils.space_indentation('  abc'), 2)
        self.assertEqual(utils.space_indentation('\n  abc'), 0)
        self.assertEqual(utils.space_indentation('   \n  abc'), 3)

class PossibleExcTypesText(unittest.TestCase):
    def test_exception_class(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            raise NotImplementedError #@
        ''')
        found = utils.possible_exc_types(raise_node)
        expected = set(["NotImplementedError"])
        self.assertEqual(found, expected)

    def test_exception_instance(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            raise NotImplementedError("Not implemented!") #@
        ''')
        found = utils.possible_exc_types(raise_node)
        expected = set(["NotImplementedError"])
        self.assertEqual(found, expected)

    def test_rethrow(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            try:
                fake_func()
            except RuntimeError:
                raise #@
        ''')
        found = utils.possible_exc_types(raise_node)
        expected = set(["RuntimeError"])
        self.assertEqual(found, expected)

    def test_nested_in_if_rethrow(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            try:
                fake_func()
            except RuntimeError:
                if another_func():
                    raise #@
        ''')
        found = utils.possible_exc_types(raise_node)
        expected = set(["RuntimeError"])
        self.assertEqual(found, expected)

    def test_nested_in_try(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            try:
                fake_func()
            except RuntimeError:
                try:
                    another_func()
                    raise #@
                except NameError:
                    pass
        ''')
        found = utils.possible_exc_types(raise_node)
        expected = set(["RuntimeError"])
        self.assertEqual(found, expected)

    def test_nested_in_try_except(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            try:
                fake_func()
            except RuntimeError:
                try:
                    another_func()
                except NameError:
                    raise #@
        ''')
        found = utils.possible_exc_types(raise_node)
        expected = set(["NameError"])
        self.assertEqual(found, expected)

    def test_no_rethrow_types(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            try:
                fake_func()
            except:
                raise #@
        ''')
        found = utils.possible_exc_types(raise_node)
        expected = set()
        self.assertEqual(found, expected)

    def test_multiple_rethrow_types(self):
        raise_node = test_utils.extract_node('''
        def my_func():
            try:
                fake_func()
            except (RuntimeError, ValueError):
                raise #@
        ''')

        v = test_utils.extract_node('ValueError')
        print("inferring valueError", v.inferred())

        v = test_utils.extract_node('RuntimeError')
        print("inferring runtimeError", v.inferred())

        found = possible_exc_types(raise_node)
        expected = set(["RuntimeError", "ValueError"])
        self.assertEqual(found, expected, (found, expected))

if __name__ == '__main__':
    unittest.main()
