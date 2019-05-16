# Distributed Space Mesa

Distributed Space Mesa is a library which supports Python's Agent Based Modeling Library Mesa. It is useable but currently only provides modest benefits to run time for large agent models (greater than 10,000 agents) over 2 processors. It can use n processors but more than 2 only provides only minimal improvements. 


## Requirements

Multi-level Mesa requires

    Mesa>=0.8.4
    NetworkX>=2.2
    Pathos>=0.2.3  

## Installation 

    pip install git+https://github.com/tpike3/distributedspace_mesa.git.

## Examples of Distributed Space Mesa

Examples of multilevel_mesa are available at [Sugarscape Development Model](https://github.com/tpike3/distributedspace-test)

These examples are various instantiations of the Sugar and Spice trading model described in Chapter 4 of *Growing Artificial Societies* by Rob Axtell and Joshua Epstein.   

## Creating a Distributed Space Mesa Instance and the Multi-level Mesa Managers

Due to complications which arise in debugging users should first use the test module to ensure there are no issues prior to running a distirbuted a model. The test model creates a pseudo disitrbuted model which mimics the behavior of DS Mesa

### Test instance of DS Mesa

    #create instance of a Mesa Model
    model =  MesaInstance(grid_height = Y, grid_width = X)

    #import main class, Space_Distribute
    from distributedspace_mesa.space_distribute import Space_Distribute_Test

    #instantiate an instance of distributespace_mesa
    ds_model = Space_Distribute_Test(model, step_finish, args = None, 
    split = 0, buffer = 6, recombine = None, recombine_args = None, 
    verbose = False, boundary_pass = 1)

    #run your model
    results = ds_model.distro_geo(num_steps)


### Instance of DS Mesa

    def step_finish(agent, pos): 

        tells model what to do when an agent passed from one processor to another finds a different situation than expected

        The step finish function requires two parameters an agent object and the position the agent wants to move too



    if __name__ == '__main__':

        #create instance of a Mesa Model
        model =  MesaInstance(grid_height = Y, grid_width = X)

        #import main class, Space_Distribute
        from distributedspace_mesa.space_distribute import Space_Distribute

        #instantiate an instance of distributespace_mesa
        ds_model = Space_Distribute(model, step_finish, args = None, 
        split = 0, buffer = 6, recombine = None, recombine_args = None, 
        verbose = False, boundary_pass = 1)

        #run your model
        results = ds_model.distro_geo(num_steps)


### Required Parameters

**model** - Users must pass in their Mesa model instance. DS then make *n* copies of the model and splits the agent population as apprioriate to be on the same portion of the grid.  

**step finish function** - Users must pass in a *step finish* function. Agents being passed from one processor to another processor make their decisions base don the status of the other processor at the end of the previous step. THey then arrive at the end of the next step. As the situation of the target location may have changed the step_finish function is necessary to ensure the User understands this and provides processors to minimize impact on emergent behavior. 


### Optional Parameters 

**args** - Additional optional arguments for the step finish function if needed.

**split** - Number of processors to use, if 0 module will idnteify number of avialable processrs and use that. Currently reocmmend user only uses 2. 

**buffer** - Number of columns into neighboring buffer.

**recombine** - Optional function for recombining data after model is complete. DS Mesa has a default function to recombine model will be used if None. 

**recombine_args** - Arguments to use in optional recombine function.

**verbose** - If True will print what attribute of the model and data collector (if used) are being combined.

**boundary_pass** - Number of times agents and cells and buffers are passed back and forth after each step. Currently, this will likely incur a significant time cost. 


## DS Mesa Approach

DS Mesa divides the space into portions, with wrap around capability (if desired) to create a torus (see figure below). Each space also has a buffer in which it stores a copy of a certain numbers of cells from its neighbors. A network using Python’s Multi-Processing pipes construct is then established between each neighboring space. Agents traversing the landscape can then see their neighbor’s status at the conclusion of the previous step and decide if based on their movement algorithm it is in their best interest be sent to the processor handling their neighbor. DS Mesa then takes care of the requirements of creating n number of copies of the model, establishing a version of the model on n processors and then linking the network of pipes so the correct processors are sending and receiving the correct buffers and agents. This set up however, has some limiting challenges. 

![How the Space is split](https://github.com/tpike3/distributedspace_mesa/blob/master/picture/Torus.png)

## Happy Modeling!





    
