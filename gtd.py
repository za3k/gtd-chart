#!/usr/bin/python
import argparse
import itertools
import os
import pipes
import shlex
import subprocess
import sys
import textwrap
from pprint import pprint
class ParseException(Exception):
    pass

class Status:
    def __init__(self, status):
        self.status = status
    def done(self):
        """Is the task marked done?  A False does not imply the task is undone, neccessarily, due to unique/rare statuses"""
        return self.status.lower() in ["done", "complete", "finished"]
    def urgent(self):
        return self.status.lower() in ["urgent"]
    def delegated(self):
        """Is the task delegated to someone?"""
        return self.status.lower().startswith("delegated")
    def delegated_to(self):
        """Who was the task delegated to?"""
        if not self.delegated():
            return None
        s = self.status.split()[1:]
        if len(s)>0 and s[0]=="to":
            s =  s[1:]
        return " ".join(s)
    @classmethod
    def parse(cls, string):
        if string.startswith("[") and string.endswith("]"):
            return cls(string[1:-1])
        else:
            raise ParseException("Status.parse called on non-status")
    @classmethod
    def instance(cls, string):
        """Is the string a valid status?  Mostly checks for square brackets."""
        try:
            cls.parse(string)
        except ParseException:
            return False
        return True
class Task:
    def __init__(self, description, context, status, goals, parent=None):
        self.description = description
        self.display_description = description
        self.context = context
        if status:
            self.status = status
        else:
            self.status = Status("")
        self.subtasks = []
        self.parent = None
        self.notes = []
        if parent:
            self.goals = parent.goals + [parent.description]
            assert(goals==self.goals or not goals)
        else:
            self.goals = goals
    def formatting(self):
        if self.status.done():
            return "[color=blue]"
        elif self.status.delegated():
            return "[color=yellow]"
        elif self.status.urgent():
            return "[color=red, fillcolor=red, style=filled]"
        else:
            return "[color=red]"
    def immediate_goal(self):
        return self.goals[-1] if self.goals else None
    @classmethod
    def parse(cls, string, parenttask=None):
        try:
            atoms = shlex.split(string)
        except ValueError:
            print(string)
            raise
        try:
            if not atoms[0]=="Do":
                raise ParseException("Task.parse called on non-task")
            task = atoms[1]
            if len(atoms) == 2: # Do <task>
                context = None
                atoms = atoms[2:]
            elif atoms[2:5] == ["in", "order", "to"]: # Do <task> in order to...
                context = None
                atoms = atoms[2:]
            elif Status.instance(atoms[2]): # Do <task> [status]
                context = None
                atoms = atoms[2:]
            else: # Do <task> <context> ... (normal)
                context = atoms[2]
                atoms = atoms[3:]
            status = None
            reasons = []
            while atoms:
                if atoms[:3] == ["in", "order", "to"]:
                    reasons.append(atoms[3])
                    atoms = atoms[4:]
                elif Status.instance(atoms[0]):
                    if len(atoms)>1:
                        raise ParseException("Status should always be last in task")
                    status = Status.parse(atoms[0])
                    atoms = atoms[1:]
                else:
                    raise ParseException("Task.parse failed (generic error)")
            reasons.reverse()
        except ParseException:
            print(shlex.split(string), file=sys.stderr)
            raise
        return cls(description=task, context=context, status=status, goals=reasons, parent=parenttask)
    @classmethod
    def instance(cls, string):
        """Does the given string represent a task?"""
        return string.lower().startswith("do")
    def __hash__(self):
        return hash(self.description)
    def __str__(self):
        return "Task(" + self.description + ")"
    def __repr__(self):
        return "Task({0}, context={1}, status={2}, goals={3})".format(repr(self.description), repr(self.context), repr(self.status), repr(self.goals))
class Goal:
    def __init__(self, description, goals, subtasks=None):
        self.description = description
        self.display_description = description
        if not subtasks:
            subtasks = []
        self.subtasks = subtasks
        self.goals = goals
        self.parent = None
    def formatting(self):
        return "[color=green]"
    def toplevel(self):
        return self.parent is None
class Note:
    def __init__(self, note):
        self.note = note
    @classmethod
    def parse(cls, string, parent=None):
        atoms = shlex.split(string)
        if not atoms[0].lower() == "note":
            raise ParseException("Note.parse called on non-note")
        if len(atoms) != 2:
            print(atoms)
            raise ParseException("Too many parameters for note (check quotes)")
        return cls(atoms[1])
    @classmethod
    def instance(cls, string):
        return shlex.split(string)[0].lower()=="note"

def parseindents(f):
    """
    Parse an indented file into a tree of strings
    """
    stack = [[]]
    for line in f.split("\n")[:-1]:
        event,value = line[0],line[1:]
        if event=="=" and (value.strip()=="" or value.strip().startswith("#")):
            continue
        if event=="=":
            stack[-1].append(value)
        elif event==">":
            stack.append([stack[-1].pop()])
        elif event=="<":
            s = stack.pop()
            stack[-1].append(s)
        else:
            print("Line: " + line)
            print("Event: " + event)
            print("Value: " + value)
            raise Exception('Invalid input event')
    return stack[0]
def parse(obj, parent=None):
    if isinstance(obj, list):
        parent = parse(obj[0], parent)
        assert(len(parent)==1)
        parent = parent[0]
        if isinstance(parent, Note):
            raise ParseException("Note cannot have children")
        children = []
        [children.extend(parse(c, parent=parent)) for c in obj[1:]]
        notes = [c for c in children if isinstance(c, Note)]
        tasks = [c for c in children if isinstance(c, Task)]
        parent.notes = notes
        return [parent] + tasks
    else:
        if Task.instance(obj):
            return [Task.parse(obj, parent)]
        elif Note.instance(obj):
            return [Note.parse(obj, parent)]
        else:
            raise ParseException("Unknown format (first word)")
def readfile(f):
    lst = []
    for p in map(parse, parseindents(subprocess.check_output(["dedent.py"], stdin=f, shell=True).decode("utf-8"))):
        if isinstance(p,list):
            lst.extend(p)
        else:
            assert(False)
    d = {x.description : x for x in lst}
    queue, lst = lst, []
    while queue:
        v = queue.pop()
        if v.goals: 
            if v.goals[-1] not in d:
                goal = Goal(v.goals[-1], goals=v.goals[:-1])
                d[v.goals[-1]] = goal
                queue.append(goal)
            elif len(v.goals[:-1])>len(d[v.goals[-1]].goals):
                goal = d[v.goals[-1]]
                goal.goals = v.goals[:-1]
                if goal not in queue:
                    queue.append(goal)
            v.parent = d[v.goals[-1]]
            v.parent.subtasks.append(v)
        lst.append(v)
    return lst
def normalize_goals(lst):
    for n in lst:
        for c in n.subtasks:
            if c.parent is None:
                c.parent = n
    for n in lst:
        goals = []
        p = n.parent
        while p:
            goals.append(p.description)
            p = p.parent
        n.goals = goals
    return lst

def flatten(trees):
    elts = set()
    queue = trees
    while queue:
        v = queue.pop()
        if v not in elts:
            elts.add(v)
            queue += v.subtasks
    return list(elts)
def graph(flat):
    d = {}
    for start in flat:
        d[start] = [end for end in start.subtasks if end in flat]
    return d
def short_label(llabel):
    t= '\\n'.join(textwrap.wrap(llabel, 20))
    if(t.strip()=="" or t.strip()=="urgent"):
        print(llabel,file=sys.stderr)
    return t
    if len(llabel)>20:
        return llabel[:17]+"..."
    else:
        return llabel
def makelabels(nodes):
    d = {}
    for x in nodes:
        if x.description not in d: 
            short = short_label(x.display_description)
            if short in d.values():
                i=2
                alt = lambda n: short+"\\\\n#{0}".format(n)
                while alt(i) in d.values():
                    i+=1
                d[x.description] = alt(i)
            else:
                d[x.description] = short
    return d
def dot(taskgraph):
    labels = makelabels(taskgraph.keys())
    dot = "digraph gtd {\nsize=\"140,10000\"\noverlap=false;\n"
    for start in taskgraph:
        dot += '"{0}" {1};\n'.format(labels[start.description], start.formatting())
        for end in taskgraph[start]:
            dot += '"{0}" -> "{1}";\n   '.format(labels[start.description], labels[end.description])
    dot += "}\n"
    uf = subprocess.Popen(["unflatten", "-f", "-l 5"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    png = subprocess.Popen(["dot", "-Tpng"], stdin=uf.stdout)
    #uf = subprocess.Popen(["dot", "-Tpng"], stdin=subprocess.PIPE)
    uf.stdin.write(bytes(dot, 'UTF-8'))

def tasks(nodes):
    return [t for t in nodes if isinstance(t,Task)]
def goals(nodes):
    return [t for t in nodes if isinstance(t,Goal)]
def top_level_goals(nodes):
    return [t for t in goals(nodes) if t.toplevel()]
def complete(nodes):
    nodes = tasks(nodes)
    return [t for t in nodes if t.status.done()]
def incomplete(nodes):
    nodes = tasks(nodes)
    return [t for t in nodes if not t.status.done()]
def only_contexts(nodes, positive_context, include_none):
    for t in tasks(nodes):
        if t.context is None and include_none:
            yield t
        elif t.context == positive_context:
            yield t
    for t in goals(nodes):
        yield t
def focus_on(nodes, node):
    for n in nodes:
        if n==node:
            yield n
        elif n.description in node.goals:
            yield n
        elif node.description in n.goals:
            yield n
def find(node_desc, nodes):
    for node in nodes:
        if node.description == node_desc:
            return node
def delegated_only(nodes):
    for t in tasks(nodes):
        if t.status.delegated():
            yield t
def abbreviated(nodes):
    for n in nodes:
        if isinstance(n, Goal) or isinstance(n.parent, Goal):
            yield n
        elif n.parent is None:
            yield n
        elif not n.parent.status.done():
            if n.status.done():
                descendants = [d for d in tasks(nodes) if n.description in d.goals]
                if descendants:
                    n.display_description = "({0}) ".format(len(descendants)+1) + n.description
            yield n

def main(args):
    parsed = readfile(args.list)
    args.list.close()
    flat = flatten(parsed)
    flat = normalize_goals(flat)
    shown = []
    if args.abbreviated:
        flat = list(abbreviated(flat))
    if args.show_goals and not args.top_level_goals:
        shown.extend(goals(flat))
    elif args.top_level_goals:
        shown.extend(top_level_goals(flat))
    if args.show_complete:
        shown.extend(complete(flat))
    if args.show_incomplete:
        shown.extend(incomplete(flat))
    if args.context or args.no_context:
        shown = list(only_contexts(shown, args.context, args.no_context))
    if args.focus:
        node = find(args.focus, shown)
        shown = list(focus_on(shown, node))
    if args.delegated_only:
        shown = list(delegated_only(shown))
    
    if args.graph:
        dot(graph(shown))
    elif args.completion:
        command, current, last = args.completion
        if last in ["", command]:
            for node in shown:
                name = node.description
                if name.startswith(current):
                    print(pipes.quote(name))
    elif args.show_delegation:
        delf = lambda x:str(x.status.delegated_to()) if x.status.delegated() else "Not delegated"
        shown.sort(key=delf)
        total = 0
        for k, g in itertools.groupby(shown, delf):
            g = list(g)
            print("{0}:".format(k))
            for t in g:
                print("\t{0}".format(t.description))
            print("\t{0} total".format(len(g)))
            total += len(g)
        print("{0} total".format(total))
    else:
        for node in shown:
            print(node.description)
        if args.include_tally:
            print("{0} total".format(len(shown)))

if __name__=='__main__':
    parser = argparse.ArgumentParser(description='Manipulate a GTD to-do list')
    parser.add_argument("--list", action="store", default='/home/zachary/journal/gtd', help='the GTD file to manipulate', type=argparse.FileType(mode='r'))
    parser.add_argument("--graph", action="store_true", help='output a visual graph of todos (output in .dot format)')
    parser.add_argument("--hide-complete", action="store_false", dest="show_complete", help="hide completed tasks")
    parser.add_argument("--hide-goals", action="store_false", dest="show_goals", help="hide goals")
    parser.add_argument("--hide-incomplete", action="store_false", dest="show_incomplete", help="hide goals which are not yet completed")
    parser.add_argument("--top-level-goals", action="store_true", help="output a list of top-level goals only")
    parser.add_argument("--context", action="store", default=None, help="show only goals in this context")
    parser.add_argument("--no-context", action="store_true", help="show goals with no explicit context")
    parser.add_argument("--omit-tally", action="store_false", dest="include_tally", help="when printing a to-do list, don't show the total")
    parser.add_argument("--focus", action="store", help="show only the ancestors and decendents of one node")
    parser.add_argument("--show-delegation", action="store_true", help="show tasks grouped by assignee")
    parser.add_argument("--delegated-only", action="store_true", help="only show delegated tasks")
    parser.add_argument("--full", action="store_false", dest="abbreviated", help="show subtasks of completed tasks")
    parser.add_argument("--completion", nargs="*")
    args = parser.parse_args()
    if args.show_delegation:
        args.show_goals = False
    if args.top_level_goals:
        args.show_complete = False
        args.show_incomplete = False
    main(args)
