"""The safe JS-subset interpreter (corpus2 gap #2).

Every behaviour here maps to a real script shape in the two corpora;
the prefix-semantics contract is the load-bearing one - whatever was
assigned before the stop is exact, because the platform executed the
same statements the same way.
"""

from pentaho_migration.reports.js_eval import evaluate_script


class TestEvaluate:
    def test_pure_literals(self):
        got, stopped = evaluate_script(
            'beenName="lodint/SeamTestAction/local"; method="getResult";',
            {}, ["beenName", "method"])
        assert stopped is None
        assert got == {"beenName": "lodint/SeamTestAction/local",
                       "method": "getResult"}

    def test_js_number_plus_string_concats(self):
        got, stopped = evaluate_script(
            'PrevYear = (YEAR - 1) + "";', {"YEAR": 2004}, ["PrevYear"])
        assert stopped is None
        assert got == {"PrevYear": "2003"}

    def test_conditional_defaulting_takes_the_platforms_branch(self):
        script = (
            'if ((territory == "default") || (null==territory)) {'
            '  territory_qry_string=" ";'
            '  territory_name="All Territories";'
            '} else {'
            "  territory_qry_string=\"AND OFFICES.TERRITORY='\""
            " + territory + \"'\";"
            '  territory_name=territory + " Territory";'
            '}')
        got, stopped = evaluate_script(
            script, {"territory": "default"},
            ["territory_qry_string", "territory_name"])
        assert stopped is None
        assert got["territory_name"] == "All Territories"
        assert got["territory_qry_string"] == " "
        # a real selection takes the else branch, building the clause
        got, _ = evaluate_script(
            script, {"territory": "EMEA"},
            ["territory_qry_string", "territory_name"])
        assert got["territory_qry_string"] == \
            "AND OFFICES.TERRITORY='EMEA'"
        assert got["territory_name"] == "EMEA Territory"

    def test_a_missing_input_reads_as_null(self):
        got, stopped = evaluate_script(
            'if (null == x) { out = "empty"; } else { out = x; }',
            {}, ["out"])
        assert stopped is None
        assert got == {"out": "empty"}

    def test_plus_equals_accumulates(self):
        got, stopped = evaluate_script(
            'msg = "a"; msg += "b"; msg += "c";', {}, ["msg"])
        assert (got, stopped) == ({"msg": "abc"}, None)

    def test_prefix_semantics_stop_at_a_method_call(self):
        # the lanit shape: literals first, then an EJB/result-set read -
        # what ran before the stop is kept, the stop is reported
        got, stopped = evaluate_script(
            'beenName="x"; rcount = dsResult.getRowCount(); other="y";',
            {}, ["beenName", "rcount", "other"])
        assert got == {"beenName": "x"}
        assert stopped and "getRowCount" in stopped

    def test_loops_and_new_are_outside_the_subset(self):
        got, stopped = evaluate_script(
            "for (i=0; i<10; i++) { x = i; }", {}, ["x"])
        assert got == {} and stopped
        got, stopped = evaluate_script(
            "d = new Date(); y = d.getFullYear();", {}, ["y"])
        assert got == {} and stopped

    def test_tostring_is_the_one_allowed_method(self):
        got, stopped = evaluate_script(
            'day = 7; out = "0" + day.toString();', {}, ["out"])
        assert (got, stopped) == ({"out": "07"}, None)

    def test_skipped_branches_are_not_evaluated(self):
        # the else branch calls a method; the taken branch must still win
        got, stopped = evaluate_script(
            'if (x == "a") { out = "ok"; } '
            'else { out = bean.explode(); }',
            {"x": "a"}, ["out"])
        assert (got, stopped) == ({"out": "ok"}, None)

    def test_oversize_scripts_are_refused(self):
        got, stopped = evaluate_script("x=1;" * 3000, {}, ["x"])
        assert got == {} and stopped
