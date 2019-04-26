# -*- coding: utf-8 -*-
"""
Created on Mon Mar 18 11:34:33 2019

@author: ymamo
"""

from pathos.multiprocessing import ProcessPool
from pathos.helpers import cpu_count
import collections
import copy
import math
import warnings
import distributed_space as ds
import itertools

#change name to prevent conflicts
from mesa import space as prespace

class Space_Distribute_Test():
    
    def __init__(self, model, step_finish, args = None, split = 0, buffer = 6,\
                 resolver = None, resolver_args = None, recombine = None,\
                 recombine_args = None, verbose = False, boundary_pass = 1):
        
        
        self.model = self.grid_adjust(model)
        #add in function to finish steps
        self.step_finish = step_finish
        self.step_args = args
        
        #Get the number of CPUs unless user specified
        if split == 0: 
            self.ncpus = cpu_count()
        else:
            self.ncpus = split
        
        
        #create the number of process available
        #self.pool = ProcessPool(nodes = self.ncpus)
        self.buffer = buffer
        
        self.multi_models = collections.OrderedDict()
        #dictionary to track when all steps on each processor complete
        self.sync_status = collections.OrderedDict() 
        #print (self.pool)
        
        #add ability for user to deconflict
        self.resolver = resolver
        self.resolver_args = resolver_args
        self.boundary_pass = boundary_pass
        
        
        
        if recombine == None: 
            self.recombine = self.recombine_default
            self.recombine_args = recombine_args
        else:
            self.recombine = recombine
            self.recombine_args = recombine_args
            
        self.verbose = verbose
        
    
    
    def grid_adjust(self, model):
        
        #create instance of distributed_space, replicating the model
        if isinstance(model.grid, prespace.MultiGrid):
            new_grid = ds.MultiGrid(width = model.grid.width, \
                                    height = model.grid.height, \
                                    torus = model.grid.torus)
        else: 
            new_grid = ds.SingleGrid(width = model.grid.width, \
                                    height = model.grid.height, \
                                    torus = model.grid.torus)
       
        #extract user grid
        try: 
            user_grid = model.grid.grid
        except ValueError: 
            print ("ABM must call instance of mesa.space as \".grid\" \
                   (i.e. self.grid in model class)")
                        
        #replace grid
        new_grid.grid = user_grid
        
        #replace space instance
        model.grid = new_grid
        
       
        return model        
 
        
    def run(self,steps):
        
       
        for step in range(steps):
                        
            print ("STEP", step)
            for splt in self.multi_models.values(): 
                #print ("steps", splt.tracker, "num agents", len(splt.schedule.agents_by_breed['agent'].keys()))
                self.sync_status[splt.grid.mod_pos] = False
                #For Debugging
                print ("STEP: ", step, splt.grid.mod_pos)
                splt.step()
                #print ("steps", splt.tracker, "num agents", len(splt.schedule.agents_by_breed['agent'].keys()))
            
            for i in range(self.boundary_pass):
            
                for splt in self.multi_models.values():
                    #print ("messages", splt.tracker, "num agents",len(splt.schedule.agents_by_breed['agent'].keys()))
                    self.message_test_right(splt)
                    self.message_test_left(splt)
                    #print ("messages", splt.tracker, "num agents", len(splt.schedule.agents_by_breed['agent'].keys()))
                        
                
                for mod_pos, splt in self.multi_models.items():
                    self.sync_status[mod_pos] = True
        
                       
        self.get_buffers()
        self.recombine()
                
        return (self.multi_models, self.model)
    
    
    def get_buffers(self): 
        '''
        Function ensures no agents are left in buses prior to concluding the
        model.
        '''
                
        for splt in self.multi_models.values(): 
            
            for v in splt.grid.bus_to_left.values():
                splt.schedule.add(v)
                                    
            for v in splt.grid.bus_to_right.values(): 
                splt.schedule.add(v)
                    
    
    def recombine_default(self):
        
        '''
        Default recombine function - User can also specify
        
        Concept: Ignores common static attributes (e.g. _seed, random, ints) 
        and collects vairbale attributes (lists, schedules, dictionaries) 
        
        '''
        #Set model as based ofr all others to extned from 
        self.model = self.multi_models[0]
        
        #Go through each prcoessor
        for proc, split in self.multi_models.items(): 
            if proc == 0: 
                pass
            else: 
                #Go through dicitonary of items for each model object
                for attr, value in split.__dict__.items():
                    #Recombine the schedule
                    if attr == 'schedule':
                        self.model.schedule._agents = {**self.model.schedule._agents, **value._agents}
                        #Make allowance for agents byt breed
                        if hasattr(self.model.schedule, "agents_by_breed"):
                            for k in self.model.schedule.agents_by_breed.keys(): 
                                self.model.schedule.agents_by_breed[k] = \
                                {**self.model.schedule.agents_by_breed[k], \
                                 **value.agents_by_breed[k]}
                            
                    #Recombine the grid
                    elif attr == 'grid':
                        self.model.grid.grid.extend(value.grid)
                    #combine data collector
                    elif attr == 'datacollector':
                        if self.model.datacollector.model_reporters != None: 
                            self.model.datacollector.model_reporters = \
                            {**self.model.datacollector.model_reporters, \
                             **value.model_reporters}
                        if self.model.datacollector.agent_reporters != None: 
                            self.model.datacollector.agent_reporters =\
                            {**self.model.datacollector.agent_reporters, \
                             **value.agent_reporters}
                        if self.model.datacollector.model_vars != None: 
                            self.model.datacollector.model_vars =\
                            {**self.model.datacollector.model_vars, \
                             **value.model_vars}
                        if self.model.datacollector.tables != None: 
                            for table in self.model.datacollector.tables.keys():
                                for row, col in self.model.datacollector.tables[table].items():
                                    self.model.datacollector.tables[table][row].\
                                    extend(value.tables[table][row])
                            
                    
                    #Recombine any default dictionaries
                    elif isinstance(value, collections.defaultdict):
                        
                        model_dict = getattr(self.model, attr)
                        set_of_keys = list(set(model_dict.keys())|set(value.keys()))
                        #determine value data type list of dictionaries or dictionary of 
                        #dictionaries
                        for first_k in set_of_keys: 
                            if type(model_dict[first_k]) == list: 
                                #iterate through
                                for k in set_of_keys: 
                                    # key is in both dictionaries
                                    if k in model_dict.keys() and k in value.keys():
                                        model_dict[k].extend(value[k])
                                    # key is in value only
                                    elif k in value.keys():
                                        model_dict[k] = value[k]
                                    #already in model but not in value
                                    else: 
                                        pass
                            
                            elif type(model_dict[first_k]) == dict:
                                for k in set_of_keys: 
                                    for k in set_of_keys: 
                                        # key is in both dictionaries
                                        if k in model_dict.keys() and k in value.keys():
                                            model_dict[k] = {**model_dict[k], **value[k]}
                                        # key is in value only
                                        elif k in value.keys():
                                            model_dict[k] = value[k]
                                        #already in model but not in value
                                        else: 
                                            pass
                                    
                            else:
                                print (attr, "\n\n")
                                warnings.warn("Cannot process data type from collections, \
                                              recommend creating own recombination method.")
                                break
                            break
                        
                        setattr(self.model, attr, model_dict)                                      
                    #For list    
                    elif type(value) == list:
                        #adds to list but does not replace
                        model_attr = getattr(self.model, attr)
                        model_attr.extend(value)
                        setattr(self.model, attr, model_attr)
                    
                    #For dict    
                    elif type(value) == dict: 
                        model_attr = getattr(self.model, attr)
                        model_attr = {**model_attr, **value}
                        setattr(self.model, attr, model_attr)
                        
                    #Assumes a static variable not recorded
                    else: 
                        #Allows user to see what attributes are recombined
                        #if verbose True
                        if self.verbose == True: 
                            print ("Model '", attr, "' considered a common variable\
                               not added to recombined model")
                        else: 
                            pass
        
    ##################################################################
    #
    #
    #           GRID SUPPORT FUNCTIONS
    #
    #
    ###################################################################
                
    def split_geo(self, split):
        
        '''
        Main function for SPLIT THE GRID section
        Helper funtion for distro_geo
               
        Splits Mesa grid into array of break points
        
        Arguments: 
            split - number of times user wants grid to split, defaults to
            number of processors
            
        TODO: Allow users to specify split with arrays        
        '''
                            
        split = (math.ceil(len(self.model.grid.grid)/split))
        
        
        for i in range(0, len(self.model.grid.grid), split):
            # Create an index range for l of n items:
            yield self.model.grid.grid[i:i+split]
            
    def reduce_cpus(self,split_grid, x_splits):
        '''
        Helper function for split adjust redcues number of CPUs to ensure 
        buffer fits within it
        '''
                
        rem = self.model.grid.width % (math.ceil(len(self.model.grid.grid)/self.ncpus))
        
        first = len(x_splits)
        self.ncpus -= 1
        #place them all in last grid
        rev_i = -2
        split_grid[-2] += split_grid[-1]
        del split_grid[-1]
        rem -= 1
        while rem > 0: 
            #Make sure it does not run over, may be impossible--TODO proof
            if first + rev_i == 0: 
                split_grid[rev_i] += split_grid[rev_i + 1][0:rem]
                rem -= rem
            else: 
                #iterate the number down across the other grids
                split_grid[rev_i] += split_grid[rev_i + 1][0:rem]
                del split_grid[rev_i +1][0:rem]
                rem -= 1
                rev_i -= 1
        
        x_splits = self.x_split(split_grid)
        
        return split_grid, x_splits
            
        
    
    def split_adjust(self, split_grid, x_splits):
        '''
        Function to ensure number of processes is compatible with size of buffer
        
        '''
        
        count = 0
        for a in range(1,len(split_grid)+1):
            if (x_splits[a] - x_splits[a-1])  < (self.buffer * 2): 
                count += 1
            else: 
                pass
        if count > 2: 
            raise ValueError ("\n\nYour buffer is longer than your grid splits, \
                              either reduce your buffer or reduce your number \
                              of processes (splits)")
        elif count == 1: 
            split_grid = list(self.split_geo(self.ncpus))
            x_splits = self.x_split(split_grid)
            
            #reduce 
            split_grid, x_splits = self.reduce_cpus(split_grid, x_splits)
            
           
            warnings.warn("Your buffer exceeds the size of one of your grid_splits,\
                          your processes have been reduced to " + str(len(x_splits)-1)+ ".")
            
            return split_grid, x_splits
        else: 
            return split_grid, x_splits
     
    def create_buffers(self, split_grid):
        '''
        Helper function for split buffer: 
            
        Creates and updates buffers for each step, ensures each buffer is 
        a seperate copy so buffer is not overriding actual grid or vice versa
        '''
        #for section in split_grid: 
        row = []
        #new.append(row)
        for rw in split_grid: 
            place = []
            row.append(place)
            for pt in rw: 
                new_pt = set()
                for each in pt: 
                    new_obj = copy.copy(each)
                    delattr(new_obj, 'model')
                    new_pt.add(new_obj)
                    
                place.append(new_pt)
                           
        return row  
    
    
    def split_buffer(self, split_grid, mod_pos):
        '''
        Creates buffers for passing to other processors so they can communicate
        status of overlapping grid area
        '''
        
        #print ('creating buffers - initial')
        buffer = {"left":[], "right":[]}
        #grid_cpy = split_grid[:]
                
        if mod_pos == 0:
            buffer["left"] = self.create_buffers(split_grid[-1][-self.buffer:])
            buffer['right'] = self.create_buffers(split_grid[1][:self.buffer])
        elif mod_pos == (len(split_grid) - 1):
            buffer['left'] = self.create_buffers(split_grid[mod_pos-1][-self.buffer:])
            buffer['right'] = self.create_buffers(split_grid[0][:self.buffer])
        else: 
            buffer['left'] = self.create_buffers(split_grid[mod_pos-1][-self.buffer:])
            buffer['right'] = self.create_buffers(split_grid[mod_pos+1][:self.buffer])
        
        return buffer    
        
    
    
    def x_split(self,split_grid):

        '''
        HELPER FUNCTION  for initial spit of ABM grid
        '''
        split_pts = [0]
        last = 0
        for section in split_grid: 
            split_pts.append(last+ len(section))
            last += len(section)
            
        return split_pts
            
        
    
    ##############################################################
    #
    #       SPLIT THE MODEL
    #
    ##############################################################
    
    def split_model(self, x_splits, split_grid, new_mod, mod_pos):
        '''
        Main function to split the model
        
        Creates number of seperate models as specificed the breaking 
        up of the grid
        
        '''
        
        
        #create the new grid
        new_mod.grid.grid = split_grid[mod_pos]
        
        #create buffer as seperate attribute in grid module
        new_mod.grid.buffer = self.split_buffer(split_grid, mod_pos)
        
        #create attribute for new_mode to reference split points
        new_mod.grid.split_pts = x_splits
        
        #create attribute in section of model to reference position
        new_mod.grid.mod_pos = mod_pos
        
        #give it a tracking number
        new_mod.tracker = mod_pos
        
        #change number of rows to actual length
        new_mod.grid.width = len(split_grid[mod_pos])
        
        #Update empties list to new dimensions
        new_mod.grid.empties = list(itertools.product(
            *(range(new_mod.grid.width), range(new_mod.grid.height))))
        
                                       
        #update the schedule
        #replace model object in time function
        new_mod.schedule.model = new_mod
        #first zero out schedule
        new_mod.schedule._agents.clear()
        #for Agents with multiple agent types
        if hasattr(new_mod.schedule, "agents_by_breed"):
            new_mod.schedule.agents_by_breed.clear()
        #add in agents from grid
        for agents in new_mod.grid.coord_iter():
            for agent in agents[0]: 
                #adjust agent position
                if mod_pos == 0: 
                    pass
                    #new_mod.grid.place_agent(agent, agent.pos)
                else: 
                    agent.pos_og = agent.pos
                    #if agent.pos[0] > 35:
                    #    print (agent.pos, mod_pos)
                    agent.pos = list(agent.pos)
                    #minus break points + accouting for arrays starting at zero
                    agent.pos[0] = agent.pos[0]-x_splits[mod_pos]
                    agent.pos = tuple(agent.pos)
                    #new_mod.grid.place_agent(agent, agent.pos)
                    #if agent.pos[0] +x_splits[mod_pos]> 35:
                    #    print (agent.pos, x_splits)
        
                    
                #add agent to schedule
                new_mod.schedule.add(agent)
                #replace agent model object
                agent.model = new_mod
                    
        #update move_function
        #Create message passing instructions
        new_mod.message = Message(mod_pos, self.ncpus, new_mod, self.step_finish,\
                                  self.step_args, self.resolver, self.resolver_args)
        #TODO: Will change agent dict order cause problems later on?
        
        return new_mod
             
    #################################################################
    #
    #
    #                 Message Pass
    #
    ################################################################
    
        
    def message_test_right(self, mod):
        '''
        Psuedo message passing function to processor on right
        
        '''        
                
        # Get Grid of where message is going
        where_to = mod.message.pass_agents_right()
        
        #create buffer for neigbor grid
        buffer_right = self.create_buffers(mod.grid.grid[-self.buffer:])
        
        #Main message function         
        self.multi_models[where_to].message.receive_left_neighbor(mod.grid.bus_to_right, \
                                                                     mod.grid.width,\
                                                                     self.multi_models[where_to], 
                                                                     buffer_right, \
                                                                     self.step_finish, \
                                                                     self.resolver, \
                                                                     self.resolver_args)
        #clear bus---if any agents coming back will be on left bus
        mod.grid.bus_to_right.clear()
                   
        
    def message_test_left(self, mod):    
       '''
       Psuedo message passing function to processor on left
       '''       
        
       where_to = mod.message.pass_agents_left()
            
       buffer_left = self.create_buffers(mod.grid.grid[:self.buffer])
    
       #Main message function 
       self.multi_models[where_to].message.receive_right_neighbor(mod.grid.bus_to_left, \
                                                                 self.multi_models[where_to].grid.width,\
                                                                 self.multi_models[where_to],\
                                                                 buffer_left, \
                                                                 self.step_finish,\
                                                                 self.resolver,\
                                                                 self.resolver_args) 
       
       #clear bus ---if any agent coming back will be on right bus
       mod.grid.bus_to_left.clear()
           
    ##################################################################
    #
    #              START FUNCTION 
    #
    ##################################################################
    
    def distro_geo(self, steps):
                
        '''
        Main function for splitting up model
        '''
        #split grid apart
        split_grid = list(self.split_geo(self.ncpus)) 
        #must adjust to ensure buffer does not exceed width of grid
        #create list of split points
        x_splits = self.x_split(split_grid)
        
        split_grid, x_splits = self.split_adjust(split_grid, x_splits)
                
        mod_pos = 0
        #Make models for each region          
        for mod in range(self.ncpus):
            #copy instance of model
            new_mod = copy.deepcopy(self.model)  
            new_mod= self.split_model(x_splits, split_grid, new_mod, mod_pos)
            #add model to master list
            self.multi_models[mod_pos] = new_mod
            #Set status of model to false for synchronization of steps
            self.sync_status[mod_pos] = False
            mod_pos += 1
        #prevent divergent copies of a single model and multiple models
        self.model = self.multi_models
               
        #agents moving but not passing--going to get stuck in buffers
        #stop
        results = self.run(steps)
        
        return results
        
        

class Message:
        '''
        Message passing class for each model 
        
        Stores left and right neighbors, finishing and resolver methods        
        '''
        
    
        def __init__(self, mod_pos, num_processes, model, step_finish, step_args, \
                     resolver, res_args):
            
            self.mod_pos = mod_pos
            self.ncpus = num_processes
            self.left = self.adj_units_left(mod_pos)
            self.right = self.adj_units_right(mod_pos)
            self.model = model
            self.step_finish = step_finish
            self.step_args = step_args
            self.resolver = resolver
            self.res_args = res_args
            
            
            
        def adj_units_left(self, mod_pos):
            
            if mod_pos == 0: 
                
                return (self.ncpus-1)
            else: 
                return mod_pos-1
            
        def adj_units_right(self,mod_pos):
            
            if mod_pos == (self.ncpus-1):
                return 0
            else: 
                return mod_pos + 1
            
        def pass_agents_left(self):
            
            return self.left
        
        def pass_agents_right(self):
            
            return self.right
        
                
        def receive_left_neighbor(self, bus, grid_width, model, buffer_left, \
                                  step_finish, resolver, resolver_args):
            
            #update buffer
            #del model.grid.buffer['left']
            model.grid.buffer['left'] = buffer_left
            
            #iterate through right bus from receiving agent, work as step
            bus_iter = list(bus.values())
            for agent,pos1 in bus_iter: 
                #print ("tansfer", agent.pos, pos, agent.model.grid.mod_pos, model.grid.mod_pos)
                #print (agent.pos, pos, agent.model.grid.mod_pos, model.grid.mod_pos)
                #Adjust position to grid
                pos = list(pos1)
                if pos[0] < 0: 
                    pos[0] = pos[0] + grid_width
                else: 
                    pos[0] = pos[0] - grid_width 
                    
                #print (agent.pos, pos, agent.model.grid.mod_pos, model.grid.mod_pos)
                pos = tuple(pos)
                #change agent model
                agent.model = model
                agent.model.schedule.add(agent)                                                
                #The order of this process is very important
                #Must maintain in-between state
                #update agent position
                step_finish(agent, pos, "right", pos1)
                
            
            #iterate through current processors left bus with new buffer and agent mix
            redo = list(model.grid.bus_to_left.values())
            for agent, bad_pos in redo:  
                #print ("restep", agent.pos,agent.model.grid.mod_pos, model.grid.mod_pos)
                agent.history.append("bad pos")
                model.schedule.add(agent)
                model.grid.place_agent(agent, agent.pos)
                del model.grid.bus_to_left[agent.unique_id]
                setattr(agent, 'model', model)
                #TODO Add in resolver
                if resolver != None: 
                    if resolver_args != None:
                        resolver(agent, bad_pos, resolver_args)
                    else: 
                        resolver(agent, bad_pos)
                else: 
                    agent.step()
                
                            
            
        
        
        def receive_right_neighbor(self, bus, grid_width, model, buffer_right,\
                                   step_finish, resolver, resolver_args):
            
            #del model.grid.buffer['right']
            model.grid.buffer['right'] = buffer_right
            
            #iterate through right bus from receiving agent, work as step
            bus_iter = list(bus.values())
            for agent,pos1 in bus_iter: 
                #print ("tansfer", agent.pos, pos, agent.model.grid.mod_pos, model.grid.mod_pos)
                #Adjust position to grid
                pos = list(pos1)
                if pos[0] < 0: 
                    pos[0] = pos[0] + grid_width
                else: 
                    pos[0] = pos[0] - grid_width # -1)
                    
                #print (agent.pos, pos, agent.model.grid.mod_pos, model.grid.mod_pos)
                pos = tuple(pos)
                #change agent model
                agent.model = model
                agent.model.schedule.add(agent)                                                
                #The order of this process is very important
                #Must maintain in-between state
                #update agent position
                self.step_finish(agent, pos, "left", pos1)
            
            #iterate through current processors left bus with new buffer and agent mix
            redo = list(model.grid.bus_to_right.values())
            for agent, bad_pos in redo:  
                #print ("restep", agent.pos,agent.model.grid.mod_pos, model.grid.mod_pos)
                agent.history.append("bad pos")
                model.schedule.add(agent)
                model.grid.place_agent(agent, agent.pos)
                del model.grid.bus_to_right[agent.unique_id]
                setattr(agent, 'model', model)
                #TODO Add in Resolver
                if resolver != None: 
                    if resolver_args != None:
                        resolver(agent, bad_pos, resolver_args)
                    else: 
                        resolver(agent, bad_pos)
                else: 
                    agent.step()
                 
                
           
                
            
            
                           
                   