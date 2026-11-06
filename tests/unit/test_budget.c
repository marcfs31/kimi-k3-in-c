/* test_budget.c - --preset auto on an 8 GB machine must select ultra.
 *
 * The ordinary reserve includes 4.70 GB of resident embeddings. Below about
 * 12 GB available that reserve does not fit, and auto used to exit 2. An
 * 8 GB terminal box (about 7 GB available once Linux is up) is the machine
 * the ultra preset was measured on. This test pins both sides: that box
 * selects ultra's 2.5 / 0.31 GB budgets, and a machine that already cleared
 * the ordinary floor still gets the trunk-first plan, not ultra.
 *
 * usage: test_budget
 */
#include <stdio.h>

#include "k3_budget.h"

static int g_fail = 0;

static void ck(int ok, const char *what, const char *detail)
{
    printf("  %s  %-44s %s\n", ok ? "PASS" : "FAIL", what, detail ? detail : "");
    if (!ok) g_fail++;
}

int main(void)
{
    K3AutoPlan p;
    char d[96];

    printf("auto budget\n");

    ck(!k3_budget_auto(0.0, 8e9, &p) && !p.ok, "unknown memory is a refusal", NULL);
    ck(!k3_budget_auto(-1.0, 8e9, &p) && !p.ok, "negative memory is a refusal", NULL);

    /* 3 GB available: 95% is 2.85 GB, under the 3.5 GB ultra floor. */
    ck(!k3_budget_auto(3.0e9, 4.0e9, &p) && !p.ok && !p.ultra,
       "3 GB available is below ultra", NULL);

    /* 7 GB available, 8 GB installed. Ordinary usable is negative. */
    ck(k3_budget_auto(7.0e9, 8.0e9, &p) && p.ok && p.ultra,
       "8 GB machine selects ultra", NULL);
    ck(p.trunk_gb == K3_ULTRA_TRUNK_GB && p.cache_gb == K3_ULTRA_CACHE_GB,
       "ultra budgets are 2.5 / 0.31 GB", NULL);
    ck(p.trunk_gb < 10.0, "8 GB machine does not pin the 111 GB trunk", NULL);

    /* Just clears the ultra floor (4 GB * 0.95 = 3.8 > 3.5) and still cannot
     * fund resident embeddings. */
    ck(k3_budget_auto(4.0e9, 8.0e9, &p) && p.ok && p.ultra,
       "4 GB available still selects ultra", NULL);

    /* 12 GB available is the first size whose ordinary usable meets the
     * 3 GB floor. It must not be rewritten into ultra. */
    ck(k3_budget_auto(12.0e9, 16.0e9, &p) && p.ok && !p.ultra,
       "12 GB available keeps the ordinary plan", NULL);
    snprintf(d, sizeof d, "trunk %.2f cache %.2f", p.trunk_gb, p.cache_gb);
    ck(p.trunk_gb == 2.5 && p.cache_gb == 0.5, "12 GB plan is trunk 2.5 / cache 0.5", d);

    /* Full residency: the trunk fits, the cache receives the rest, ultra stays off. */
    ck(k3_budget_auto(200.0e9, 256.0e9, &p) && p.ok && !p.ultra,
       "200 GB available is not ultra", NULL);
    snprintf(d, sizeof d, "trunk %.2f cache %.2f", p.trunk_gb, p.cache_gb);
    ck(p.trunk_gb == 111.0 && p.cache_gb > 50.0,
       "200 GB pins the 111 GB trunk and caches the rest", d);

    /* total unknown: the partial-pin cap falls back to usable, and the plan
     * still exists. A zero total must not look like "no memory". */
    ck(k3_budget_auto(32.0e9, 0.0, &p) && p.ok && !p.ultra && p.trunk_gb > 0.0,
       "unknown total still produces a plan", NULL);

    printf("\n%s\n", g_fail ? "BUDGET TESTS FAILED" : "BUDGET TESTS PASSED");
    return g_fail ? 1 : 0;
}
