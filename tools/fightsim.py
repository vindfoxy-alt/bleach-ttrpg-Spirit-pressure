"""Spirit Pressure fight simulator (simplified Monte Carlo).

A party of 4 (the tested hero + 3 baseline fighters) fights a boss and 2 minions.
Enemy strength is calibrated per level so an all-baseline party wins ~60%.
Result = win rate with the hero in the party.  Simplified: it is a rough guide, not a rules engine.
"""
import random, statistics, json, sys

LV = [3, 8, 13, 18]
PROF = {3: 2, 8: 3, 13: 5, 18: 6}
MOD = {3: 3, 8: 4, 13: 5, 18: 5}      # main attack modifier
CON = {3: 2, 8: 2, 13: 3, 18: 3}
RP_FIGHT = 0.5                         # fraction of max RP available per fight (several fights per rest)

def d(n, s): return n * (s + 1) / 2

class H:
    """A combatant. attacks = list of (to_hit, avg_dmg) per attack action."""
    def __init__(s, hp, ac, atks, name="", rp=0):
        s.hp = s.maxhp = hp; s.ac = ac; s.atks = atks; s.name = name; s.rp = rp
        s.buffs = []          # active buff dicts
        s.abil = []           # abilities (see cfg)
        s.once = set()
        s.resist = 0.0; s.dis = 0.0; s.ac_bonus = 0.0
        s.hits_round = 0
        s.dealt = 0.0; s.timer = 3; s.dead = False; s.dupl = 0; s.wall = 0; s.ac_all = 0
    @property
    def alive(s): return s.hp > 0

def baseline(L):
    ac = {3: 14, 8: 15, 13: 16, 18: 17}[L]
    hp = (6 + 2) * L + 6
    atks = [(PROF[L] + MOD[L], 4.5 + MOD[L] + 2)] * {3: 1, 8: 2, 13: 2, 18: 3}[L]
    h = H(hp, ac, atks, "base"); h.cls = "base"; h.rpmax = 0; h.rp = 0; h.L = L
    return h

PERSONA = ["brute", "focus", "assassin", "hunter", "bully"]

def enemies(L, k, rng=None):
    b = {3: (60, 14, 6, 2, 8), 8: (150, 16, 9, 2, 16), 13: (260, 17, 11, 3, 20), 18: (380, 18, 13, 3, 28)}[L]
    hp, ac, th, n, dm = b
    boss = H(int(hp * k), ac, [(th, dm * (0.8 + 0.2 * k))] * n, "boss")
    m = [H(int(hp * k * 0.3), ac - 2, [(th - 2, dm * 0.55 * (0.8 + 0.2 * k))], "min") for _ in range(2)]
    for e in [m[0], m[1], boss]:
        e.persona = rng.choice(PERSONA) if rng else "brute"
    return [m[0], m[1], boss]

def hit_p(th, ac, adv=0):
    p = min(0.95, max(0.05, (21 - (ac - th)) / 20))
    if adv > 0: p = 1 - (1 - p) ** 2
    if adv < 0: p = p * p
    return p

# ---------------- hero builders -----------------
def chassis(cls, L):
    m, p = MOD[L], PROF[L]
    if cls == "sr":
        h = H((5.5 + 2) * L + 6 + 2, {3: 14, 8: 15, 13: 16, 18: 17}[L], [(p + m, 4.5 + m + 2)] * {3: 1, 8: 2, 13: 2, 18: 3}[L], "sr")
        h.rpmax = 2 * L + m
    elif cls == "qu":
        die = {3: 4.5, 8: 4.5, 13: 5.5, 18: 6.5}[L]
        h = H((4.5 + 2) * L + 4, {3: 14, 8: 15, 13: 16, 18: 16}[L], [(p + m, die + m)] * {3: 1, 8: 2, 13: 2, 18: 2}[L], "qu")
        h.rpmax = 2 * L + m
        h.ranged = True
        h.conc = p            # Concentrated Shot: up to prof RP, +1d6 each
    elif cls == "hb":
        claw = {3: 3.5, 8: 4.5, 13: 5.5, 18: 6.5}[L]
        sd = {3: 2, 8: 2, 13: 3, 18: 4}[L]
        h = H((7 + 3) * L + 8, 10 + 3 + CON[L] // 2, [(p + m, claw + m)] * {3: 1, 8: 2, 13: 2, 18: 2}[L], "hb")
        h.rpmax = 2 * L + CON[L] + 1
        h.surge = sd
        h.cero = {3: 10.5, 8: 14, 13: 28, 18: 35}[L]
    else:  # fb
        h = H((4.5 + 2) * L + 4, {3: 13, 8: 14, 13: 15, 18: 15}[L], [(p + m, 5.5 + m + (3.5 if L >= 13 else 0))] * {3: 1, 8: 2, 13: 2, 18: 2}[L], "fb")
        h.rpmax = 2 * L + m
    h.cls = cls; h.L = L
    h.rp = h.rpmax * RP_FIGHT
    h.maxhp = h.hp = int(h.hp)
    return h

# Subclass config: lists of effects.  Each effect: dict(kind, cost, ...)
#  buff:  once at start, cost, effects while active: xd (extra dmg per hit), xdfirst (extra dmg on first hit/round), ac, resist, dis (enemy attack disadvantage fraction),
#         tmp (temporary HP), atk (extra attacks), crit (extra hit chance), xhit (to-hit bonus), aura (dmg to every enemy per round), heal_r (HP per round to hero), speed
#  act:   per round action ability: aoe (dmg to all enemies, 0.7 expected), ctrl (chance to remove one enemy attack-set), heal (to lowest ally), dmg (single target)
#  react: per round while RP: shield allies (ac_party) etc.
def sub(cls, name, L):
    h = chassis(cls, L)
    A = []
    surge = getattr(h, "surge", 0)
    if cls == "hb":
        A.append(dict(kind="buff", cost=2, resist=0.5, xd=surge, heal_r=PROF[L], nofocus=1))
        A.append(dict(kind="act", cost=3, aoe=h.cero, name="cero", targets=2))
    if cls == "sr":
        A.append(dict(kind="buff", cost=2, xd=0, name="shikai"))
    if cls == "qu":
        A.append(dict(kind="buff", cost=0, name="conc"))
    if cls == "fb":
        A.append(dict(kind="act", cost=2, ctrl=0.25, name="cling"))
    # ---- subclasses ----
    T = L >= 2; S = L >= 6; U = L >= 11; X = L >= 17
    if name == "Yamamoto":
        xd = (3.5 if L < 9 else 3.5) + (3.5 if U else 0)
        if L >= 9 and not U: xd = 3.5
        A.append(dict(kind="buff", cost=0, xd=xd + 2.5 * 0.7, resist=0.1))       # +1d4/1d6 fire + burn
        if S: A.append(dict(kind="act", cost=3, aoe={8: 14, 13: 21, 18: 28}[L], targets=3, name="enjo"))
        if U: A.append(dict(kind="buff", cost=6, aura=7, tmpspeed=1, once=True))
    elif name == "Aizen":
        A.append(dict(kind="buff", cost=0, dis=0.4))
        A.append(dict(kind="act", cost=3, dupl=1, name="dup"))                  # duplicates: absorb attacks
        if U: A.append(dict(kind="buff", cost=6, dis=0.5, xhit=3, once=True))
        if X: A.append(dict(kind="buff", cost=0, aura=10))
    elif name == "Zaraki":
        h.maxhp += (L + 3); h.hp = h.maxhp
        h.atks = [(t, 7 + (h.atks[0][1] - 4.5 - 2 - MOD[L] + MOD[L])) for t, _ in h.atks]
        A.append(dict(kind="buff", cost=0, xd=4.5 * 0.5))
        if U: A.append(dict(kind="buff", cost=6, xd=3.5, adv=1, ctrl_aura=0.15, once=True))
    elif name == "Urahara":
        A.append(dict(kind="buff", cost=0, ctrl_hit=0.4))
        if S: A.append(dict(kind="act", cost=2, heal=10.5 + 4, name="kaido"))
        if U: A.append(dict(kind="buff", cost=6, slow=0.5, heal_all=3.5, once=True))
        if X: A.append(dict(kind="act", cost=4, aoe={17: 28, 18: 30}.get(L, 30), targets=2, name="k6"))
    elif name == "Uryū Ishida":
        A.append(dict(kind="buff", cost=0, advfirst=1, xdfirst=3.5 * 0.5))
        if S: A.append(dict(kind="buff", cost=0, xd=2.0))
        if U: A.append(dict(kind="buff", cost=6, crit=0.1, xdfirst=7, once=True))
        if X: A.append(dict(kind="buff", cost=0, xd=3.0))
    elif name == "Sōken Ishida":
        h.ac += 1
        A.append(dict(kind="buff", cost=0, atk=1))
        if S: A.append(dict(kind="buff", cost=2, xd=7 * 0.5, rpdrain=1))
        if U: A.append(dict(kind="buff", cost=6, atk=2, xd=2, once=True))
        h.ranged = False
    elif name == "Haschwalth":
        A.append(dict(kind="react", cost=1, ac_party=3))
        if S: A.append(dict(kind="buff", cost=3, ac_all=0.25, once=True))
        if U: A.append(dict(kind="buff", cost=6, ac_all=2, retaliate=3.5, once=True))
        if X: A.append(dict(kind="buff", cost=0, saveall=1))
    elif name == "Bazz-B":
        A.append(dict(kind="buff", cost=1, xd=3.5 + 3.5 * 0.6 * 2))            # +1d6 fire + burning over rounds
        if S: A.append(dict(kind="act", cost=3, aoe=17.5, targets=3, name="burst"))
        if U: A.append(dict(kind="buff", cost=6, xd=3.5, once=True))
        if X: A.append(dict(kind="buff", cost=0, aura=7))
    elif name == "Shinji Hirako":
        h.hb_free_surge = True
        A.append(dict(kind="buff", cost=0, xd=0, shinji=1))
        if S: A.append(dict(kind="buff", cost=2, xdfirst=10.5, name="maskburst"))
        if U: A.append(dict(kind="buff", cost=6, xhit=2, xd=2, tmp=20, once=True))
    elif name == "Grimmjow":
        A.append(dict(kind="buff", cost=1, xdfirst=4.5 * 0.7, name="pounce"))
        if U: A.append(dict(kind="buff", cost=6, atk=1, xd=h.atks[0][1] * 0.5, once=True, bigdie=1))
        if X: A.append(dict(kind="buff", cost=0, crit=0.1))
    elif name == "Yammy":
        h.ac += 1
        A.append(dict(kind="buff", cost=0, tmp=L + 3))
        if S: A.append(dict(kind="react", cost=2, selfred=6.5 + 3))
        if U: A.append(dict(kind="buff", cost=6, ac=4, resist=0.5, thorns=7, once=True))
    elif name == "Ulquiorra":
        for a in A:
            if a.get("name") == "cero": a["cost"] = 2; a["aoe"] = a["aoe"] + 7 * 0.5
        if S: A.append(dict(kind="act", cost=1, dmg=4.5 * 3 * 0.6, name="bala"))
        if U: A.append(dict(kind="buff", cost=6, ceromult=1.4, once=True))
        if X: A.append(dict(kind="act", cost=10, aoe=66, targets=1, name="oscuras", once=True))
    elif name == "Ginjō":
        h.ac += 1
        A.append(dict(kind="buff", cost=0, xd=2.5))
        if S: A.append(dict(kind="act", cost=2, aoe=10.5, targets=2, name="slash"))
        if U: A.append(dict(kind="buff", cost=6, ac=2, xd=3.5, once=True))
        if X: A.append(dict(kind="buff", cost=0, resist=0.5, xdfirst=4.5))
    elif name == "Riruka":
        A.append(dict(kind="buff", cost=0, rpfree=1))
        if S: A.append(dict(kind="act", cost=3, shrink=0.45, name="addiction"))
        if U: A.append(dict(kind="buff", cost=6, xd=4.5, dis=0.25, once=True))
        if X: A.append(dict(kind="buff", cost=0, dis=0.2))
    elif name == "Tsukishima":
        A.append(dict(kind="act", cost=1, advnext=1, name="insert"))
        if S: A.append(dict(kind="react", cost=2, replay=1))
        if U: A.append(dict(kind="buff", cost=6, aura=18 * 0.55, ctrl_aura=0.1, once=True))
        if X: A.append(dict(kind="act", cost=8, undo=1, name="recall", once=True))
    elif name == "Orihime":
        A.append(dict(kind="act", cost=2, heal=7 + 4 + 3, name="soten"))
        A.append(dict(kind="react", cost=1, ac_party=2))
        if S: A.append(dict(kind="act", cost=3, wall=40, name="santen"))
        if U: A.append(dict(kind="buff", cost=6, heal_mult=2, once=True))
        if X: A.append(dict(kind="act", cost=10, revive=1, name="revive", once=True))
    h.abil = A
    return h

SUBS = {
    "sr": ["Yamamoto", "Aizen", "Zaraki", "Urahara"],
    "qu": ["Uryū Ishida", "Sōken Ishida", "Haschwalth", "Bazz-B"],
    "hb": ["Shinji Hirako", "Grimmjow", "Yammy", "Ulquiorra"],
    "fb": ["Ginjō", "Riruka", "Tsukishima", "Orihime"],
}

# ---------------- fight -----------------
# Personalities decide whom an enemy attacks:
#   brute    - any living party member at random
#   focus    - the member with the lowest HP percentage (finishes the wounded)
#   assassin - the squishiest member: lowest AC, ties by lowest max HP
#   hunter   - whoever has dealt the most damage so far (goes after the biggest threat)
#   bully    - the member with the most HP left (tests the tank), otherwise random
def pick_target(e, party, rng):
    up = [p for p in party if p.hp > 0]
    if not up: return None
    ps = getattr(e, "persona", "brute")
    if ps == "focus": return min(up, key=lambda p: p.hp / p.maxhp)
    if ps == "assassin": return min(up, key=lambda p: (p.ac + p.ac_bonus_now(), p.maxhp))
    if ps == "hunter": return max(up, key=lambda p: (p.dealt, rng.random()))
    if ps == "bully": return max(up, key=lambda p: p.hp)
    return rng.choice(up)

def _ac_bonus_now(self): return getattr(self, "ac_bonus", 0)
H.ac_bonus_now = _ac_bonus_now

def d20(rng, adv=0):
    a, b = rng.randint(1, 20), rng.randint(1, 20)
    return max(a, b) if adv > 0 else min(a, b) if adv < 0 else a

def reserve(h):
    c = [a["cost"] for a in h.abil if a["kind"] == "act" and "heal" in a]
    return min(c) if c else 0

def fight(party, foes, rng, maxr=12):
    hero = party[0]
    stat = {"hero_dmg": 0, "hero_heal": 0, "saved": 0}
    for h in party: h.maxrp = h.rp
    for rnd in range(1, maxr + 1):
        if not any(e.alive for e in foes): return True, rnd, stat
        if not any(p.hp > 0 for p in party): return False, rnd, stat
        # ---- party turns ----
        for idx, h in enumerate(party):
            alive_f = [e for e in foes if e.alive]
            if not alive_f: break
            if h.hp <= 0: continue
            if idx > 0:
                tgt = alive_f[0]
                for t, dm in h.atks:
                    if tgt.hp <= 0:
                        r = [e for e in foes if e.alive]
                        if not r: break
                        tgt = r[0]
                    adv = 1 if getattr(tgt, "marked", 0) else 0
                    roll = d20(rng, adv)
                    if roll == 20 or (roll != 1 and roll + t >= tgt.ac):
                        dm_ = dm * (2 if roll == 20 else 1)
                        tgt.hp -= dm_; h.dealt += dm_
                if getattr(alive_f[-1], "marked", 0): alive_f[-1].marked = 0
                continue
            # ---------- hero ----------
            for a in h.abil:
                if a["kind"] != "buff": continue
                key = id(a)
                if key in h.once: continue
                if a["cost"] <= h.rp:
                    if a.get("once") and rnd < 2: continue
                    h.rp -= a["cost"]; h.once.add(key); h.buffs.append(a)
            xd = sum(b.get("xd", 0) for b in h.buffs)
            xdfirst = sum(b.get("xdfirst", 0) for b in h.buffs)
            xhit = sum(b.get("xhit", 0) for b in h.buffs)
            crit = sum(b.get("crit", 0) for b in h.buffs)
            xatk = sum(b.get("atk", 0) for b in h.buffs)
            adv = 1 if any(b.get("advfirst") or b.get("adv") for b in h.buffs) else 0
            tmp = sum(b.get("tmp", 0) for b in h.buffs)
            h.resist = min(0.8, sum(b.get("resist", 0) for b in h.buffs))
            h.dis = min(0.6, sum(b.get("dis", 0) for b in h.buffs))
            h.ac_bonus = sum(b.get("ac", 0) for b in h.buffs)
            h.ac_all = sum(b.get("ac_all", 0) for b in h.buffs)
            if rnd == 1 or not hasattr(h, "tmp_done"):
                h.hp += tmp; h.maxhp += tmp; h.tmp_done = True
            h.hp = min(h.maxhp, h.hp + sum(b.get("heal_r", 0) for b in h.buffs))
            heal_all = sum(b.get("heal_all", 0) for b in h.buffs)
            if heal_all:
                for p in party:
                    if p.hp > 0: p.hp = min(p.maxhp, p.hp + heal_all)
            aura = sum(b.get("aura", 0) for b in h.buffs)
            for e in alive_f:
                e.hp -= aura * 0.7; h.dealt += aura * 0.7; stat["hero_dmg"] += aura * 0.7
            ca = sum(b.get("ctrl_aura", 0) for b in h.buffs)
            if ca:
                for e in alive_f:
                    if rng.random() < ca: e.stunned = True
            # action ability
            acts = sorted([a for a in h.abil if a["kind"] == "act"], key=lambda a: 0 if ("heal" in a or "revive" in a) else 1)
            hurt = [p for p in party if p.hp < 0.5 * p.maxhp]            # includes downed (hp <= 0)
            for a in acts:
                if a["cost"] > h.rp: continue
                if a.get("once") and id(a) in h.once: continue
                if "heal" in a:
                    if not hurt: continue
                    t = min(hurt, key=lambda p: p.hp / p.maxhp)
                    amt = a["heal"] * (2 if any(b.get("heal_mult") for b in h.buffs) else 1)
                    if t.hp <= 0: t.hp = 0; t.timer = 3
                    t.hp = min(t.maxhp, t.hp + amt); stat["hero_heal"] += amt
                    h.rp -= a["cost"]; break
                if "revive" in a:
                    dead = [p for p in party if p.dead]
                    if not dead: continue
                    p = dead[0]; p.dead = False; p.hp = 1; p.timer = 3
                    h.once.add(id(a)); h.rp -= a["cost"]; break
                if "aoe" in a:
                    tg = alive_f[:a.get("targets", 3)]
                    m = 1.4 if (a.get("name") == "cero" and any(b.get("ceromult") for b in h.buffs)) else 1.0
                    if a.get("once"): h.once.add(id(a))
                    for e in tg:
                        e.hp -= a["aoe"] * 0.7 * m; h.dealt += a["aoe"] * 0.7 * m; stat["hero_dmg"] += a["aoe"] * 0.7 * m
                    h.rp -= a["cost"]; break
                if "shrink" in a:
                    boss = alive_f[-1]
                    if rng.random() < a["shrink"] and not getattr(boss, "shrunk", 0):
                        boss.stunned = True; boss.shrunk = 2
                    h.rp -= a["cost"]; break
                if "ctrl" in a:
                    boss = alive_f[-1]
                    if rng.random() < a["ctrl"]: boss.stunned = True
                    h.rp -= a["cost"]; break
                if "dupl" in a:
                    h.dupl = 3; h.rp -= a["cost"]; break
                if "wall" in a:
                    h.wall = a["wall"]; h.rp -= a["cost"]; break
                if "advnext" in a:
                    alive_f[-1].marked = 1; h.rp -= a["cost"]; break
                if "dmg" in a:
                    alive_f[0].hp -= a["dmg"]; h.dealt += a["dmg"]; stat["hero_dmg"] += a["dmg"]; h.rp -= a["cost"]; break
            n = len(h.atks) + xatk
            tgt = alive_f[0]; first = True
            base_hit = h.atks[0][0] + xhit; base_dm = h.atks[0][1]
            if any(b.get("bigdie") for b in h.buffs): base_dm *= 1.4
            conc = getattr(h, "conc", 0)
            for i in range(n):
                if tgt.hp <= 0:
                    r = [e for e in foes if e.alive]
                    if not r: break
                    tgt = r[0]
                extra = xd + (xdfirst if first else 0)
                if conc and h.rp >= conc and i == 0:
                    spend = min(conc, int(h.rp * 0.4)); extra += 3.5 * spend; h.rp -= spend
                a_ = adv if first else 0
                if getattr(tgt, "marked", 0): a_ = 1
                roll = d20(rng, a_)
                cr = roll >= 20 - int(crit * 20)
                if cr or (roll != 1 and roll + base_hit >= tgt.ac):
                    dm_ = (base_dm + extra) * (1.8 if cr else 1)
                    tgt.hp -= dm_; h.dealt += dm_; stat["hero_dmg"] += dm_
                    if h.cls == "qu": h.rp = min(h.rpmax, h.rp + 1)
                first = False
            if getattr(alive_f[-1], "marked", 0): alive_f[-1].marked = 0
        # ---- enemy turns ----
        for e in [x for x in foes if x.alive]:
            if getattr(e, "stunned", False):
                e.stunned = False
                if getattr(e, "shrunk", 0):
                    e.shrunk -= 1
                    if e.shrunk > 0: e.stunned = True
                continue
            for t_, dm_ in e.atks:
                tgt = pick_target(e, party, rng)
                if tgt is None: break
                if tgt.dupl > 0 and rng.random() < 0.6:
                    tgt.dupl -= 1; continue
                ac = tgt.ac + tgt.ac_bonus_now() + (hero.ac_all if tgt is not hero and hero.hp > 0 else 0)
                adv = -1 if (tgt is hero and rng.random() < hero.dis) else 0
                roll = d20(rng, adv)
                hit = roll == 20 or (roll != 1 and roll + t_ >= ac)
                # hero reactions: shield an ally (or self) when a hit would be turned into a miss
                if hit and roll != 20 and hero.hp > 0:
                    for a in hero.abil:
                        if a["kind"] == "react" and "ac_party" in a and hero.rp - a["cost"] >= reserve(hero) and roll + t_ < ac + a["ac_party"]:
                            hero.rp -= a["cost"]; hit = False; stat["saved"] += dm_; break
                    if hit:
                        for a in hero.abil:
                            if a["kind"] == "react" and "replay" in a and tgt is not hero and hero.rp - a["cost"] >= reserve(hero):
                                hero.rp -= a["cost"]
                                r2 = d20(rng, -1)
                                hit = r2 == 20 or (r2 != 1 and r2 + t_ >= ac)
                                if not hit: stat["saved"] += dm_
                                break
                if not hit: continue
                dm = dm_
                if tgt is hero:
                    dm *= (1 - hero.resist)
                    sr = [a for a in hero.abil if a.get("selfred")]
                    if sr and hero.rp >= 2: hero.rp -= 2; dm = max(0, dm - sr[0]["selfred"])
                if tgt is not hero and hero.wall > 0 and rng.random() < 0.5:
                    ab = min(dm, hero.wall); hero.wall -= ab; dm -= ab; stat["saved"] += ab
                if tgt.hp > 0 and tgt.hp - dm <= 0 and tgt is hero and getattr(hero, "bond_save", False) is False and hero.cls == "fb":
                    hero.bond_save = True; tgt.hp = 1; continue
                tgt.hp -= dm
                th = sum(b.get("thorns", 0) + b.get("retaliate", 0) for b in hero.buffs)
                if th and tgt is hero: e.hp -= th * 0.8
                if tgt.hp <= 0: tgt.timer = 3
        # ---- end of round: downed members bleed out ----
        for p in party:
            if p.hp <= 0 and not p.dead:
                p.timer -= 1
                if p.timer <= 0: p.dead = True; p.hp = -999
    return (not any(e.alive for e in foes)), maxr, stat

def run(party_fn, L, k, n=1500, seed=1):
    rng = random.Random(seed)
    wins = 0; rounds = []; hd = []
    for _ in range(n):
        party = party_fn(); foes = enemies(L, k, rng)
        ok, r, st = fight(party, foes, rng)
        wins += ok; rounds.append(r); hd.append(st["hero_dmg"] + st["hero_heal"] + st["saved"])
    return wins / n, statistics.mean(rounds), statistics.mean(hd)

def calibrate(L, target=0.60):
    lo, hi = 0.3, 3.0
    for _ in range(14):
        k = (lo + hi) / 2
        w, *_ = run(lambda: [baseline(L) for _ in range(4)], L, k, n=500, seed=7)
        if w > target: lo = k
        else: hi = k
    return (lo + hi) / 2
