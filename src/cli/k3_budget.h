/* k3_budget.h - pure sizing for --preset auto.
 *
 * The ordinary plan reserves 4.70 GB for resident embeddings. On an 8 GB
 * machine that reserve is larger than memory, so auto used to exit before it
 * could select the ultra preset, which streams those tables. That is the
 * budget an 8 GB terminal box can actually admit. At and above the ordinary
 * floor the split is the previous trunk-first plan, unchanged.
 *
 * No allocation and no I/O. k3_run.c passes in the probe results.
 */
#ifndef K3_BUDGET_H
#define K3_BUDGET_H

/* Shared with the admission check in k3_run.c. The two must use one number:
 * a plan sized to a higher fraction than the check allows refuses itself. */
#define K3_MEM_ADMIT 0.95

/* The "ultra" row of K3_PRESETS in k3_run.c. test_budget pins both sites. */
#define K3_ULTRA_TRUNK_GB 2.5
#define K3_ULTRA_CACHE_GB 0.31
/* 95% of available must cover the two budgets plus half a gigabyte for the
 * streamed tables and scratch. The detailed plan in k3_run.c still refuses
 * a prompt that needs more than this. */
#define K3_ULTRA_FLOOR_GB 3.5

typedef struct {
    int    ok;         /* 1: plan is usable. 0: avail unknown, or below ultra. */
    int    ultra;      /* 1: ordinary reserve does not fit; stream embeddings. */
    double trunk_gb;
    double cache_gb;
    double avail_gb;
    double reserve_gb; /* ordinary-path reserve, also when ultra is chosen */
} K3AutoPlan;

static inline int k3_budget_auto(double avail, double total, K3AutoPlan *p)
{
    const double slot_min = 2.5;    /* one ring slot + headroom */
    const double cache_min = 0.5;   /* topk+1 expert slots is ~0.3 GB */
    const double trunk_full = 111.0;

    p->ok = 0;
    p->ultra = 0;
    p->trunk_gb = 0.0;
    p->cache_gb = 0.0;
    p->avail_gb = 0.0;
    p->reserve_gb = 0.0;
    if (!(avail > 0.0)) return 0;

    p->avail_gb = avail / 1e9;
    /* Embeddings + lm_head 4.70 GB, recurrent state and the safetensors index
     * 1.70 GB, 2 GB for buffers and the KV cache, plus the fraction the
     * admission check holds back. */
    p->reserve_gb = 2.0 + (1.0 - K3_MEM_ADMIT) * p->avail_gb + 4.70 + 1.70;
    {
        const double usable = p->avail_gb - p->reserve_gb;
        if (usable < slot_min + cache_min) {
            if (p->avail_gb * K3_MEM_ADMIT < K3_ULTRA_FLOOR_GB) return 0;
            p->ok = 1;
            p->ultra = 1;
            p->trunk_gb = K3_ULTRA_TRUNK_GB;
            p->cache_gb = K3_ULTRA_CACHE_GB;
            return 1;
        }
        if (usable - cache_min >= trunk_full) {
            p->trunk_gb = trunk_full;
            p->cache_gb = usable - trunk_full;
        } else {
            const double rss_ceiling = total > 0.0 ? 0.55 * total / 1e9 : usable;
            double cap = rss_ceiling - p->reserve_gb - cache_min;
            if (cap < slot_min) cap = slot_min;
            p->trunk_gb = usable - cache_min;
            if (p->trunk_gb > cap) p->trunk_gb = cap;
            p->cache_gb = cache_min;
        }
        p->ok = 1;
        return 1;
    }
}

#endif
