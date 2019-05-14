# -*- coding: utf-8 -*-
"""
Created on Mon Mar 18 11:34:33 2019

@author: ymamo
"""

from pathos.pools import ProcessPool
from pathos.helpers import cpu_count, mp
import collections
import copy
import math
import warnings
import distributedspace_mesa.distributed_space as ds
import itertools
#from pympler import asizeof
import time


#change name to prevent conflicts
from mesa import space as prespace

class Space_Distribute():
    
    def __init__(self, model, step_finish, args = None, split = 0, buffer = 6,\
                 recombine = None,recombine_args = None, verbose = False, \
                 boundary_pass = 1):
        
        
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
        self.pool = ProcessPool(nodes = self.ncpus)
        self.pipes = self.pipe_setup(self.ncpus)
        
        self.buffer = buffer
        self.multi_models = collections.OrderedDict()
        #dictionary to track when all steps on each processor complete
        self.sync_status = collections.OrderedDict() 
        
        
        #add ability for user to deconflict
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
 
        
    def run(self, steps, model, pipes):
        
        '''
        Data Structure for pipes: 
            [[reader_from_left, writer_to left],[reader_from_right, writer_to_right]]
            eg for 3 processors: 
                2 to 0           0 to 2             1 to 0             0 to 1
        '''
        
        #stop
        for i in range(steps):
            #print ("step", i)
            #Wait for step- Goes True line 118,119
            while model.message.left_finish == False or model.message.right_finish == False: 
                time.sleep(0.01)
            
            else: 
                
                model.message.left_finish = False
                model.message.right_finish = False                
                model.step()
                            
                for i in range(self.boundary_pass):
                    #Function turn send_right, receive_right, receive_left... to False
                    #Message turns values to True
                    
                    model.message.send_prep(i)
                    while model.message.receive_right_complete == False or\
                    model.message.send_right_complete == False or\
                    model.message.receive_left_complete == False or \
                    model.message.send_left_complete == False: 
                        
                        if model.message.send_right_complete == False:
                            model.message.send_right(pipes[1][1])
                        
                        if model.message.send_left_complete == False: 
                            model.message.send_left(pipes[0][1])
                            
                        if model.message.receive_left_complete == False: 
                            model.message.receive_left(pipes[0][0])
                                            
                        if model.message.receive_right_complete == False: 
                            model.message.receive_right(pipes[1][0])
                   
                    else: 
                        model.message.process_left_neighbor()
    
                        model.message.process_right_neighbor()
                        
                        model.message.send_complete_right(pipes[1][1])
                        model.message.send_complete_left(pipes[0][1])
                        
                        model.message.receive_left(pipes[0][0])
                        model.message.receive_right(pipes[1][0])
                        
        #close pipes
        for pipe in pipes: 
            for end in pipe:
                end.close()
        
        #make sure no agents in buffers
        self.get_buffers(model)
        
                
        return model
    
    
    def get_buffers(self,model): 
        '''
        Function ensures no agents are left in buses prior to concluding the
        model.
        '''
                
        for v in model.grid.bus_to_left.values():
                
            model.schedule.add(v[0])
                                    
        for v in model.grid.bus_to_right.values(): 
            
            model.schedule.add(v[0])
                    
    
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
        
        #new_mod.size = asizeof.asizeof            
        #update move_function
        new_mod.message = Message(mod_pos, self.ncpus, new_mod, \
                                  self.step_finish, \
                                  self.step_args,self.buffer)
        #TODO: Will change agent dict order cause problems later on?
        
        return new_mod
             
    #################################################################
    #
    #
    #                 Message Pass
    #
    ################################################################
    
    def pipe_setup(self, number_processes):
        
        pipes = {"left" : [], "right" : []}
        
        #create pipe objects
        for k in range(number_processes):  
            reader, writer = mp.Pipe()
            pipes['left'].append([reader, writer, k])
            reader2, writer2 = mp.Pipe()
            pipes['right'].append([reader2,writer2, k])
                                  
        return pipes
            
    def pipe_assign(self):
        
        assign_pipe = []
        
        for i in range(self.ncpus):
            assign_pipe.append([[],[]])
        
        for i in (range(self.ncpus)) :
            right = self.multi_models[i].message.right
            left = self.multi_models[i].message.left
            #assign reader from left
            assign_pipe[i][0].insert(0, self.pipes['left'][i][0])
            #assign writer to left
            assign_pipe[i][0].insert(1, self.pipes['right'][left][1])
            #assign reader to right
            assign_pipe[i][1].insert(0, self.pipes['right'][i][0])
            #assign writer to right
            assign_pipe[i][1].insert(1, self.pipes['left'][right][1])
        
        return assign_pipe
    
   
    
           
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
        #self.model = self.multi_models
        
        step_list = [steps] * self.ncpus
        #print (step_list)
        
        models = list(self.multi_models.values())
        #print ("model size", asizeof.asizeof(models))
        #Create message passing instructions
               
        pipes_list = self.pipe_assign() 

        results = self.pool.map(self.run, step_list, models, pipes_list)
                
        for i in range(len(results)):
            self.multi_models[i] = results[i]
            
        self.recombine()
        
        #stop
        #results = self.run(steps)
        
        return (results, self.model)
        
        

class Message:
        '''
        Message passing class for each model 
        
        Stores left and right neighbors, and finishing method        
        '''
        
    
        def __init__(self, mod_pos, num_processes, model, step_finish,\
                     step_args, buffer):
            
            self.mod_pos = mod_pos
            self.ncpus = num_processes
            self.left = self.adj_units_left(mod_pos)
            self.right = self.adj_units_right(mod_pos)
            self.model = model
            self.step_finish = step_finish
            self.step_args = step_args
            self.buffer = buffer
            self.left_finish = True
            self.right_finish = True
            self.send_left_complete = False
            self.send_right_complete = False
            self.receive_right_complete = False
            self.receive_left_complete = False
            self.right_bus = {}
            self.right_new_buffer = self.create_dummy_buffer(self.buffer)
            self.right_width = None
            self.right_buffer_x = 0
            self.right_buffer_y = 0
            self.left_bus = {}
            self.left_new_buffer = self.create_dummy_buffer(self.buffer)
            self.left_width = None
            self.left_buffer_x = 0
            self.left_buffer_y = 0
            self.bus_left_keys = 0
            self.bus_right_keys = 0
            self.width_sent_right = False
            self.width_sent_left = False
            self.right_sent_buffer_x = 0
            self.right_sent_buffer_y = 0
            self.left_sent_buffer_x = 0
            self.left_sent_buffer_y = 0
            
                      
            
            
            
        def create_dummy_buffer(self, buffer):
            
            dummy_buffer = []
            
            for row in range(buffer):
                dummy_buffer.append([])
                
            return dummy_buffer
            
            
        
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
                        if hasattr(new_obj, 'model'):
                            delattr(new_obj, 'model')
                        new_pt.add(new_obj)
                    place.append(new_pt)
                    
            return row
        
        def send_prep(self,iteration):
            
            self.bus_right_keys = list(self.model.grid.bus_to_right.keys())
            self.bus_left_keys = list(self.model.grid.bus_to_left.keys())
            self.right_sent_buffer_x = 0
            self.right_sent_buffer_y = 0
            self.left_sent_buffer_x = 0
            self.left_sent_buffer_y = 0
            self.right_buffer_x = 0
            self.right_buffer_y = 0
            self.left_buffer_x = 0
            self.left_buffer_y = 0
            self.receive_right_complete = False
            self.receive_left_complete = False
            self.send_right_complete = False
            self.send_left_complete = False
            self.left_new_buffer = self.create_dummy_buffer(self.buffer)
            self.right_new_buffer = self.create_dummy_buffer(self.buffer)
            
               
        def send_right(self, pipe):
            
            #send the bus
            if len(self.bus_right_keys) > 0: 
                               
                pipe.send(((self.bus_right_keys[0],\
                           self.model.grid.bus_to_right[self.bus_right_keys[0]]), "bus"))
                  
                del self.model.grid.bus_to_right[self.bus_right_keys[0]]
                del self.bus_right_keys[0]
                
            elif self.width_sent_right == False: 
                #send the width
                pipe.send((self.model.grid.width, "width"))
                self.width_sent_right = True
                
            elif self.right_sent_buffer_x < self.buffer:
                     
                     cell = self.model.grid.buffer["right"][self.right_sent_buffer_x][self.right_sent_buffer_y]
                                          
                     #print ("cell size", asizeof.asizeof(cell), self.right_sent_buffer_x,self.right_sent_buffer_y)
                     pipe.send((cell, "buffer"))
                     if self.right_sent_buffer_y < self.model.grid.height-1:
                         self.right_sent_buffer_y += 1
                     else:
                        self.right_sent_buffer_x += 1
                        self.right_sent_buffer_y = 0
                     #print ("cell", self.right_sent_buffer_x,self.right_sent_buffer_y)
            else:
                 #Send complete statement
                 pipe.send((None, "complete"))
                 self.send_right_complete = True
        
        def send_complete_right(self, pipe):
            pipe.send((None, "left_finished"))
            
        def receive_right(self, pipe):
                                    
            message = pipe.recv()
                       
            
            if message[1] == "bus": 
                self.right_bus[message[0][0]] = message[0][1]
            
            #TODO Clean this up, unnecessary     
            elif message[1] == "width":
                self.right_width = self.model.grid.width
                
            elif message[1] == "buffer":
                self.right_new_buffer[self.right_buffer_x].insert(self.right_buffer_y, message[0])
                
                self.right_buffer_y += 1
                
                if self.right_buffer_y == self.model.grid.height:
                    
                    self.right_buffer_y = 0
                    self.right_buffer_x += 1
                    
            elif message[1] == "complete": 
                self.receive_right_complete = True
                
            elif message[1] == "right_finished":
                self.right_finish = True
                
            elif message[1] == "step_complete":
                self.right_step_finished = True
            
            elif message[1] == "right_message":
                self.right_messaging_finished = True
            
            else: 
                raise ValueError("Message Error")                 
                
        
        def send_left(self, pipe):
            
            #send the bus
            if len(self.bus_left_keys) > 0: 
                
                pipe.send(((self.bus_left_keys[0],\
                           self.model.grid.bus_to_left[self.bus_left_keys[0]]), "bus"))
                                
                del self.model.grid.bus_to_left[self.bus_left_keys[0]]
                del self.bus_left_keys[0]
                
                
            elif self.width_sent_left == False: 
                #send the width
                pipe.send((self.model.grid.width, "width"))
                self.width_sent_left = True
                
            elif self.left_sent_buffer_x < self.buffer:
                     cell = self.model.grid.buffer["left"][self.left_sent_buffer_x][self.left_sent_buffer_y]
   
                     pipe.send((cell, "buffer"))
                     if self.left_sent_buffer_y < self.model.grid.height-1:
                         self.left_sent_buffer_y += 1
                     else:
                        self.left_sent_buffer_x += 1
                        self.left_sent_buffer_y = 0
            else:
                 
                 #Send complete statement
                 pipe.send((None, "complete"))
                 self.send_left_complete = True
            
            
        def send_complete_left(self, pipe):
            
            pipe.send((None, "right_finished"))
                         
        
        def receive_left(self, pipe):
                                    
            message = pipe.recv()
           
            if message[1] == "bus": 
                self.left_bus[message[0][0]] = message[0][1]
               
            elif message[1] == "width":
                self.left_width = message[0]
                
            elif message[1] == "buffer":
                
                self.left_new_buffer[self.left_buffer_x].insert(self.left_buffer_y, message[0])
                
                self.left_buffer_y += 1
                
                if self.left_buffer_y == self.model.grid.height:
                    self.left_buffer_y = 0
                    self.left_buffer_x += 1
                    
            elif message[1] == "complete": 
                self.receive_left_complete = True
                
            elif message[1] == "left_finished":
                self.left_finish = True
                
            elif message[1] == "step_complete":
                self.left_step_finished = True
                
            elif message[1] == "left_message":
                self.left_messaging_finished = True
            
            
            else: 
                raise ValueError("Message Error")  
                
       
               
        def process_left_neighbor(self):
            
            #update buffer
            #del model.grid.buffer['left']
            #TODO: Optimization point
            self.model.grid.buffer['left'] = self.left_new_buffer
            #iterate through right bus from receiving agent, work as step
            bus_iter = list(self.left_bus.values())
            for agent,pos1 in bus_iter: 
                #Adjust position to grid
                pos = list(pos1)
                if pos[0] < 0: 
                    pos[0] = pos[0] + self.left_width
                else: 
                    pos[0] = pos[0] - self.left_width    
                pos = tuple(pos)
                #change agent model
                agent.model = self.model
                agent.model.schedule.add(agent)                                                
                #The order of this process is very important
                #Must maintain in-between state
                #update agent position
                if self.step_args == None: 
                    self.step_finish(agent, pos) #, "right", pos1)
                else: 
                    self.step_finish(agent, pos, self.step_args)
                del self.left_bus[agent.unique_id]
            
                
        def process_right_neighbor(self):
            
            #del model.grid.buffer['right']
            self.model.grid.buffer['right'] = self.right_new_buffer
            #iterate through right bus from receiving agent, work as step
            bus_iter = list(self.right_bus.values())
            for agent,pos1 in bus_iter: 
                #Adjust position to grid
                pos = list(pos1)
                if pos[0] < 0: 
                    pos[0] = pos[0] + self.model.grid.width
                else: 
                    pos[0] = pos[0] - self.model.grid.width
                    
                pos = tuple(pos)
                #change agent model
                agent.model = self.model
                agent.model.schedule.add(agent)                                                
                #The order of this process is very important
                #Must maintain in-between state
                #update agent position
                if self.step_args == None: 
                    self.step_finish(agent, pos) #, "right", pos1)
                else: 
                    self.step_finish(agent, pos, self.step_args)
                del self.right_bus[agent.unique_id]
                
            
                
           
                
            
            
                           
                   