import random

import sc2
from sc2 import Race, Difficulty
from sc2.constants import *
from sc2.player import Bot, Computer
from sc2.player import Human

import time
import math


class Lakers(sc2.BotAI):
    def __init__(self, use_model=True):
        self.combinedActions = []
        self.enemy_expand_location = None
        self.first_supply_built=False
        self.stage = "early_rush"
        self.depot_pos1 = None
        self.depot_pos2 = None
        self.corner = None
        self.upgradesIndex = 0
        self.counter_units = {
            #Enemy: [Enemy_Cunts, Army, Num]
            MARINE: [3, SIEGETANK, 1],
            MARAUDER: [3, MARINE, 3],
            REAPER: [3, SIEGETANK, 3],
            GHOST: [2, MARINE, 3],
            SIEGETANK: [1, BANSHEE, 1],
            BANSHEE: [1, MARINE, 3]
            }
        self.engineeringUpgrades = [ENGINEERINGBAYRESEARCH_TERRANINFANTRYWEAPONSLEVEL1,ENGINEERINGBAYRESEARCH_TERRANINFANTRYARMORLEVEL1,
                                    ENGINEERINGBAYRESEARCH_TERRANINFANTRYWEAPONSLEVEL2,ENGINEERINGBAYRESEARCH_TERRANINFANTRYARMORLEVEL2,
                                    ENGINEERINGBAYRESEARCH_TERRANINFANTRYWEAPONSLEVEL3,ENGINEERINGBAYRESEARCH_TERRANINFANTRYARMORLEVEL3]        

    async def on_game_start(self):
        for worker in self.workers:
            closest_mineral_patch = self.state.mineral_field.closest_to(worker)
            self.combinedActions.append(worker.gather(closest_mineral_patch))
            await self.do_actions(self.combinedActions)
        self.enemy_expand_location = await self.find_enemy_expand_location()
		
        self.corner = self.main_base_ramp.corner_depots
        self.depot_pos1 = self.corner.pop()
        self.depot_pos2 = self.corner.pop()

    async def find_enemy_expand_location(self):
        closest = None
        distance = math.inf
        for el in self.expansion_locations:
            def too_near_to_expansion(t):
                return t.position.distance_to(el) < self.EXPANSION_GAP_THRESHOLD

            if too_near_to_expansion(sc2.position.Point2(self.enemy_start_locations[0])):
                continue

            d = await self._client.query_pathing(self.enemy_start_locations[0], el)
            if d is None:
                continue

            if d < distance:
                distance = d
                closest = el
        return closest

    async def on_step(self, iteration):
        if iteration == 0:
            await self.on_game_start()
            return
        cc = self.units(COMMANDCENTER).ready
        if not cc.exists:
            self.worker_rush(iteration)
            return
      
        if self.stage == "early_rush":
            await self.early_rush(iteration)
            return
        #await self.main_progress(iteration)


    async def early_rush(self, iteration):
        cc = self.units(COMMANDCENTER).ready.first
        #采矿
        await self.distribute_workers()
        await self.adjust_workers(cc)
        #造农民
        await self.train_WORKERS(cc)
        #1.房子，第一个堵路口
        await self.build_rush_SUPPLYDEPOT(cc)
        
        #2. 气矿
        await self.build_REFINERY(cc)

        # 升级
        if self.units(FACTORY).amount >= 1:
            await self.build_ENGINEERINGBAY(cc)
        await self.upgrader()
        await self.upgrade_army_buildings()
        
        #3. 兵营
        await self.build_rush_BARRACKS(cc)
        
        #4. 枪兵
        await self.train_MARINE()
		
	    #5. 工厂
        await self.build_FACTORY(cc)
		
        #6. 坦克
        await self.train_SIEGETANK()

        await self.move_to_corner()
		
	# 坦克x2  机枪兵x14
        if self.units(SIEGETANK).amount >= 2:
            await self.do_rush(iteration)
       
        
    # Start
    async def main_progress(self, iteration):
        #await self.worker_rush(iteration)
        await self.worker_detect(iteration)
        #await self.marine_detect(iteration)
        cc = self.units(COMMANDCENTER).ready
        if not cc.exists:
            self.worker_rush(iteration)
            return
        else:
            cc = cc.first

        ############### 修建筑 ####################
        await self.build_SUPPLYDEPOT(cc)      # 修建补给站
        await self.build_BARRACKS(cc)         # 修建兵营
        await self.build_FACTORY(cc)          # 修建重工厂
        await self.build_STARPORT(cc)         # 修建星港
        await self.build_ENGINEERINGBAY(cc)   # 修建工程站
        #await self.build_SENSORTOWER(cc)      # 修建感应塔
        #await self.build_MISSILETURRET(cc)    # 修建导弹他
        #await self.build_GHOSTACADEMY(cc)     # 修建幽灵学院
        #await self.build_BUNKER(cc)           # 修建地堡
        await self.build_REFINERY(cc)         # 修建精炼厂

        ################ 采矿 ######################
        await self.distribute_workers()
        for a in self.units(REFINERY):
            if a.assigned_harvesters < a.ideal_harvesters:
                w = self.workers.closer_than(20, a)
                if w.exists:
                    await self.do(w.random.gather(a))

        ################ 训练 ######################
        await self.train_WORKERS(cc)      # 训练农民
        await self.train_MARINE()         # 训练机枪兵
        #await self.train_MARAUDER()       # 训练掠夺者
        #await self.train_REAPER()         # 训练收割者
        #await self.train_GHOST()          # 训练幽灵
        #await self.train_SIEGETANK()      # 训练坦克
        await self.train_BANSHEE()        # 训练女妖战机

        ############### 进攻 ###################
        # 当机枪兵大于16个时，进攻
        #if self.units(MARINE).amount > 15:
        #    for marine in self.units(MARINE):
        #        await self.do(marine.attack(self.enemy_start_locations[0]))

        # 机枪兵大于10个，女妖大于3，进攻
        if self.units(MARINE).amount > 10 and self.units(BANSHEE).amount > 3:
            for ma in self.units(MARINE):
                await self.do(ma.attack(self.enemy_start_locations[0]))
            for bs in self.units(BANSHEE):
                await self.do(bs.attack(self.enemy_start_locations[0]))

    ############ 功能函数 ################
    async def adjust_workers(self, cc):
        for idle_worker in self.workers.idle:
            mf = self.state.mineral_field.closest_to(cc.position)
            self.combinedActions.append(idle_worker.gather(mf))
                
    async def worker_rush(self, iteration):
        self.actions = []
        target = self.enemy_start_locations[0]
        if iteration == 0:
            for worker in self.workers:
                self.actions.append(worker.attack(target))
        await self.do_actions(self.actions)
		
    async def do_rush(self, iteration):
        self.actions = []
        target = self.enemy_start_locations[0]
        for marine in self.units(MARINE):
            self.actions.append(marine.attack(target))
        for tank in self.units(SIEGETANK):
            self.actions.append(tank.attack(target))				
        await self.do_actions(self.actions)		

    async def worker_detect(self, iteration):
        self.actions = []
        target = self.enemy_start_locations[0]
        if iteration != 0 and iteration / 15 == 0:
            for worker in self.workers:
                self.actions.append(worker.attack(target))
                break
        await self.do_actions(self.actions)

    async def marine_detect(self, iteration):
        self.actions = []
        target = self.enemy_start_locations[0]
        if iteration != 0 and iteration / 10 == 0:
            for unit in self.units(MARINE):
                self.actions.append(unit.attack(target))
                break
        await self.do_actions(self.actions)

    async def train_WORKERS(self, cc):
        for cc in self.units(COMMANDCENTER).ready.noqueue:
            workers = len(self.units(SCV).closer_than(15, cc.position))
            minerals = len(self.state.mineral_field.closer_than(15, cc.position))
            if minerals > 4:
                if workers < 18:
                    if self.can_afford(SCV):
                        await self.do(cc.train(SCV))

    async def build_rush_SUPPLYDEPOT(self, cc):
    #   第一个房子，堵路口
        if self.units(SUPPLYDEPOT).amount < 1 and self.supply_left <= 7 and self.can_afford(SUPPLYDEPOT) and not self.already_pending(SUPPLYDEPOT): # and not self.first_supply_built:
            await self.build(SUPPLYDEPOT, near=self.depot_pos1)
        elif self.units(SUPPLYDEPOT).amount == 1 and self.supply_left <= 7 and self.can_afford(SUPPLYDEPOT) and not self.already_pending(SUPPLYDEPOT): 
            await self.build(SUPPLYDEPOT, near=self.depot_pos2)
        else:
            await self.build_SUPPLYDEPOT(cc)
            
        

    async def build_SUPPLYDEPOT(self, cc):
        if self.supply_left <= 5 and self.can_afford(SUPPLYDEPOT) and not self.already_pending(SUPPLYDEPOT): # and not self.first_supply_built:
            await self.build(SUPPLYDEPOT, near = cc.position, random_alternative=False)


    async def build_rush_BARRACKS(self, cc):     
        if self.units(BARRACKS).amount == 0 and self.can_afford(BARRACKS):
            await self.build(BARRACKS, near = cc.position.towards(self.game_info.map_center, 6))
            
        if self.units(BARRACKS).amount == 1 and self.can_afford(BARRACKS):
            await self.build(BARRACKS, near = cc.position.towards(self.game_info.map_center, 11))

    async def build_BARRACKS(self, cc):
        if self.units(BARRACKS).amount == 0 and self.can_afford(BARRACKS):
            await self.build(BARRACKS, near = cc.position.towards(self.game_info.map_center, 9))
        if self.units(BARRACKS).amount < 3 and self.units(FACTORY).ready.exists and self.can_afford(BARRACKS):
            await self.build(BARRACKS, near = cc.position.towards(self.game_info.map_center, 9))
        if self.units(BARRACKS).amount < 5 and self.units(STARPORT).ready.exists and self.can_afford(BARRACKS):
            await self.build(BARRACKS, near = cc.position.towards(self.game_info.map_center, 9))

    async def build_FACTORY(self, cc):
        if self.stage == "early_rush":
            if self.units(FACTORY).amount < 1 and self.units(BARRACKS).ready.exists and self.can_afford(FACTORY) and not self.already_pending(FACTORY):
                await self.build(FACTORY, near = cc.position.towards(self.game_info.map_center, 15))
            for sp in self.units(FACTORY).ready:
                if sp.add_on_tag == 0:
                    await self.do(sp.build(FACTORYTECHLAB))
            return	
			
        if self.units(FACTORY).amount < 3 and self.units(BARRACKS).ready.exists and self.can_afford(FACTORY) and not self.already_pending(FACTORY):
            await self.build(FACTORY, near = cc.position.towards(self.game_info.map_center, 9))
        # 修建 FACTORYTECHLAB, 以建造坦克
        for sp in self.units(FACTORY).ready:
            if sp.add_on_tag == 0:
                await self.do(sp.build(FACTORYTECHLAB))

    async def build_STARPORT(self, cc):
        if self.units(STARPORT).amount < 3 and self.units(FACTORY).ready.exists and self.can_afford(STARPORT) and not self.already_pending(STARPORT):
            await self.build(STARPORT, near = cc.position.towards(self.game_info.map_center, 9))
        # 修建 STARPORTTECHLAB, 以建女妖
        for sp in self.units(STARPORT).ready:
            if sp.add_on_tag == 0:
                await self.do(sp.build(STARPORTTECHLAB))

    async def build_ENGINEERINGBAY(self, cc):
        if self.units(ENGINEERINGBAY).amount < 1 and self.can_afford(ENGINEERINGBAY) and not self.already_pending(ENGINEERINGBAY):
            await self.build(ENGINEERINGBAY, near = cc.position.towards(self.game_info.map_center, 9))

    async def build_SENSORTOWER(self, cc):
        if self.units(SENSORTOWER).amount < 2 and self.units(ENGINEERINGBAY).ready.exists and self.can_afford(SENSORTOWER) and not self.already_pending(SENSORTOWER):
            await self.build(SENSORTOWER, near = cc.position.towards(self.game_info.map_center, 9))

    async def build_MISSILETURRET(self, cc):
        if self.units(MISSILETURRET).amount < 4 and self.units(SENSORTOWER).ready.exists and self.can_afford(MISSILETURRET) and not self.already_pending(MISSILETURRET):
            #await self.build(MISSILETURRET, near = cc.position.towards(self.game_info.map_center, 9))
            ramp = self.main_base_ramp.corner_depots
            cm = self.units(COMMANDCENTER)
            ramp = {d for d in ramp if cm.closest_distance_to(d) > 1}
            target = ramp.pop()
            await self.build(MISSILETURRET, near=target)

    async def build_GHOSTACADEMY(self, cc):
        if self.units(GHOSTACADEMY).amount < 1 and self.units(FACTORY).ready.exists and self.can_afford(GHOSTACADEMY) and not self.already_pending(GHOSTACADEMY):
            await self.build(GHOSTACADEMY, near = cc.position.towards(self.game_info.map_center, 9))

    async def build_BUNKER(self, cc):
        if self.units(BUNKER).amount < 5 and self.units(GHOSTACADEMY).ready.exists and self.can_afford(BUNKER) and not self.already_pending(BUNKER):
            await self.build(BUNKER, near = cc.position.towards(self.game_info.map_center, 9))

    async def build_rush_REFINERY(self, cc):		
        if self.units(REFINERY).amount < 1 and not self.already_pending(REFINERY):
            await self.build_REFINERY(cc)
        elif self.units(FACTORY).amount >=1 and not self.already_pending(REFINERY):
            await self.build_REFINERY(cc)

    async def build_REFINERY(self, cc):
        #if self.units(REFINERY).amount < 2 and self.can_afford(REFINERY):
        #    await self.build(REFINERY, near = cc.position.towards(self.game_info.map_center, 9))
		
        if self.units(BARRACKS).exists and self.units(REFINERY).amount < 2 and self.can_afford(REFINERY) and not self.already_pending(REFINERY):
            vgs = self.state.vespene_geyser.closer_than(20.0, cc)
            for vg in vgs:
                if self.units(REFINERY).closer_than(1.0, vg).exists:
                    break
                worker = self.select_build_worker(vg.position)
                if worker is None:
                    break
                await self.do(worker.build(REFINERY, vg))
                break

    # 训练机枪兵
    async def train_MARINE(self):
        if self.stage == "early_rush":
            do_train = False
            if self.units(MARINE).amount < 6 and self.can_afford(MARINE):
                do_train = True
            elif self.units(BARRACKSTECHLAB).amount + self.units(BARRACKSREACTOR).amount >= 2:
                do_train = True
            if do_train:
                for barrack in self.units(BARRACKS).ready.noqueue:
                    await self.do(barrack.train(MARINE))


        # 训练掠夺者
    async def train_MARAUDER(self):
        if self.units(MARAUDER).amount < 5 and self.can_afford(MARAUDER):
            for marauder in self.units(BARRACKS).ready:
                await self.do(marauder.train(MARAUDER))

    # 训练收割者
    async def train_REAPER(self):
        if self.units(REAPER).amount < 5 and self.can_afford(REAPER):
            for re in self.units(BARRACKS).ready:
                await self.do(re.train(REAPER))

    # 训练幽灵
    async def train_GHOST(self):
        if self.units(GHOST).amount < 5 and self.can_afford(GHOST):
            for gst in self.units(GHOSTACADEMY).ready:
                await self.do(gst.train(GHOST))

    # 训练坦克
    async def train_SIEGETANK(self):
        if self.units(SIEGETANK).amount < 5 and self.can_afford(SIEGETANK):
            for st in self.units(FACTORY).ready:
                await self.do(st.train(SIEGETANK))

    # 训练女妖战机
    async def train_BANSHEE(self):
        if self.units(BANSHEE).amount < 5 and self.can_afford(BANSHEE):
            for bs in self.units(STARPORT).ready:
                await self.do(bs.train(BANSHEE))

    #移动到路口
    async def move_to_corner(self):
        self.actions = []
        for unit in self.units(MARINE):
            self.actions.append(unit.move(self.depot_pos1))
        for unit in self.units(SIEGETANK):
            self.actions.append(unit.move(self.depot_pos2))
        await self.do_actions(self.actions)
            
            



# 升级相关

    async def upgrader(self):
      #if self.upgradesIndex >1:
      #  if len(self.units(ARMORY)) < 1:
      #      if not self.already_pending(ARMORY):
      #          if not self.units(FACTORY).exists:
      #              if not self.already_pending(FACTORY):
      #                  if self.can_afford(FACTORY):
      #                      await self.build(FACTORY, near = self.units(COMMANDCENTER)[0])
      #          else:
      #              if self.can_afford(ARMORY):
      #                  await self.build(ARMORY, near = self.units(COMMANDCENTER)[0])
        if self.stage == "early_rush":
            # 早期只升1级机枪兵
            if self.upgradesIndex < 2:
                for EB in self.units(ENGINEERINGBAY).ready.noqueue:
                    if self.upgradesIndex < len(self.engineeringUpgrades):
                        if self.can_afford(self.engineeringUpgrades[self.upgradesIndex]):
                            await self.do(EB(self.engineeringUpgrades[self.upgradesIndex]))
                            self.upgradesIndex+=1



    async def ammendFlyingList(self,rax):
        destination = await self.find_placement(COMMANDCENTER, near =rax.position,max_distance = 100)
        if destination != None:
            self.flyingBarracks.append([rax,destination,0])
            await self.do(rax.move(destination))


    async def upgrade_army_buildings(self):
        if self.units(BARRACKS).ready.amount == 0:
            return
            
        techlabs = len(self.units(BARRACKSTECHLAB))
        reactors = len(self.units(BARRACKSREACTOR))
        
        for b in self.units(BARRACKS).ready.noqueue:
            if not b.has_add_on:
                if not b.is_flying:
                    if reactors < techlabs:
                        if self.can_afford(BARRACKSTECHLAB):
                           await self.do(b.build(BARRACKSTECHLAB))
                           #if not b.has_add_on:
                           #     await self.do(b(LIFT_BARRACKS))
                                #await self.ammendFlyingList(b)
                        
                    else:
                        if self.can_afford(BARRACKSREACTOR):
                            await self.do(b.build(BARRACKSREACTOR))
                            #if not b.has_add_on:
                                #await self.ammendFlyingList(b)
                                #await self.do(b(LIFT_BARRACKS))
                            #    if not b.has_add_on:
                            #        await self.do(b(LIFT_BARRACKS))
                                    #await self.ammendFlyingList(b)

def main():
    sc2.run_game(sc2.maps.get("PortAleksanderLE"), [
        Bot(Race.Terran, Lakers()),
        Computer(Race.Terran, Difficulty.Easy)
        #Human(Race.Terran)
    ], realtime=False)

if __name__ == '__main__':
    main()

