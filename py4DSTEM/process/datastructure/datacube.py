# Defines a class - DataCube - for storing / accessing / manipulating the 4D-STEM data
# The DataCube class has a single child class, RawDataCube, also defined here.
#
# DataCube objects contain a 4DSTEM dataset, attributes describing its shape, and methods
# pointing to processing functions - generally defined in other files in the process directory.
#
# RawDataCube objects inherit from DataCube objects, and additionally contain functionality to:
#    -be instantiated from a read-in file
#    -store metadata from raw files
#    -track data objects created in reference to this raw dataset in a DataObjectTracker (see
#     dataobjecttracker.py)
# RawDatacube objects can be generated by the read_data() function, which accepts a filepath and 
# outputs a RawDatacube.
# py4DSTEM processing pipelines are saved as .h5 files with the save_from_datacube() function,
# which accepts a RawDataCube, and spit out a .h5 file.  The default behavior is to saw the 
# RawDataCube and all objects related to it, defined in its DataObjectTracker. Instead of
# storing the complete set of data, any object in the DataObjectTracker (including the
# RawDataCube itself) can have its name and log info, but not raw data, saved by setting the
# 'save' Boolean in the tracker to False. The existance of these objects is thus saved, and the
# objects may be recreated using the log info.

from hyperspy.misc.utils import DictionaryTreeBrowser
from .. import preprocess
from .dataobject import DataObject, DataObjectTracker

class DataCube(DataObject):

    def __init__(self, data, R_Ny, R_Nx, Q_Ny, Q_Nx, parent):
        """
        Instantiate a DataCube object. Set the data, scan dimensions, and metadata.
        """
        DataObject.__init__(self, parent=parent)

        # Initialize DataCube, set dimensions
        self.data4D = data
        self.R_Ny, self.R_Nx = R_Ny, R_Nx
        self.Q_Ny, self.Q_Nx = Q_Ny, Q_Nx
        self.R_N = R_Ny*R_Nx
        self.set_scan_shape(self.R_Ny,self.R_Nx)

    ############### Processing functions, organized by file in process directory ##############

    ############### preprocess.py ##############

    def set_scan_shape(self,R_Ny,R_Nx):
        """
        Reshape the data given the real space scan shape.
        """
        self = preprocess.set_scan_shape(self,R_Ny,R_Nx)

    def crop_data_diffraction(self,crop_Qy_min,crop_Qy_max,crop_Qx_min,crop_Qx_max):
        self = preprocess.crop_data_diffraction(self,crop_Qy_min,crop_Qy_max,crop_Qx_min,crop_Qx_max)

    def crop_data_real(self,crop_Ry_min,crop_Ry_max,crop_Rx_min,crop_Rx_max):
        self = preprocess.crop_data_real(self,crop_Ry_min,crop_Ry_max,crop_Rx_min,crop_Rx_max)

    def bin_data_diffraction(self, bin_factor):
        self = preprocess.bin_data_diffraction(self, bin_factor)

    def bin_data_real(self, bin_factor):
        self = preprocess.bin_data_real(self, bin_factor)



    ################ Slice data #################

    def get_diffraction_space_view(self,y=0,x=0):
        """
        Returns the image in diffraction space, and a Bool indicating success or failure.
        """
        self.x,self.y = x,y
        try:
            return self.data4D[y,x,:,:].T, 1
        except IndexError:
            return 0, 0

    def get_real_space_view(self,slice_y,slice_x):
        """
        Returns the image in diffraction space.
        """
        return self.data4D[:,:,slice_y,slice_x].sum(axis=(2,3)).T, 1

########################## END OF DATACUBE OBJECT ########################


class RawDataCube(DataCube):

    def __init__(self, data, R_Ny, R_Nx, Q_Ny, Q_Nx,
                 is_py4DSTEM_file=False, h5_file=None,
                 original_metadata_shortlist=None, original_metadata_all=None):
        """
        Instantiate a RawDataCube object.
        Sets the data and scan dimensions.
        Additionally handles metadata in one of two ways - either for native py4DSTEM files, or
        for non-native files.
        """
        # Initialize RawDataCube, set dimensions
        DataCube.__init__(self, data, R_Ny, R_Nx, Q_Ny, Q_Nx, parent=None)

        # Set up DataObjectTracker
        self.dataobjecttracker = DataObjectTracker(self)

        # Handle metadata
        if is_py4DSTEM_file:
            self.setup_metadata_py4DSTEM_file(h5_file)
        else:
            self.setup_metadata_hs_file(original_metadata_shortlist, original_metadata_all)

    ###################### METADATA HANDLING ########################
    # Metadata is structured as follows:
    # In datacube instance d = Datacube() contains an empty class called d.metadata.
    # d.metadata contains:
    #     -an empty class called d.metadata.original, containing two
    #      hyperspy.misc.utils.DictionaryTreeBrowser objects with the original metadata.
    #     -five dictionary objects with all metadata which this program uses, either scraped
    #      from the original metadata or generated by other means
    #################################################################

    def setup_metadata_py4DSTEM_file(self, h5_file):
        self.setup_metadata_containers()
        self.setup_metadata_search_dicts()

        # Copy original metadata from .h5 trees to an equivalent tree structure
        self.metadata.original.shortlist = MetadataCollection('shortlist')
        self.metadata.original.all = MetadataCollection('all')
        self.get_original_metadata_from_h5_file(h5_file['4DSTEM_experiment']['metadata']['original']['shortlist'],self.metadata.original.shortlist)
        self.get_original_metadata_from_h5_file(h5_file['4DSTEM_experiment']['metadata']['original']['all'],self.metadata.original.all)

        # Copy metadata from .h5 groups to corresponding dictionaries
        self.get_metadata_from_h5_file(h5_file['4DSTEM_experiment']['metadata']['microscope'],self.metadata.microscope)
        self.get_metadata_from_h5_file(h5_file['4DSTEM_experiment']['metadata']['sample'],self.metadata.sample)
        self.get_metadata_from_h5_file(h5_file['4DSTEM_experiment']['metadata']['user'],self.metadata.user)
        self.get_metadata_from_h5_file(h5_file['4DSTEM_experiment']['metadata']['calibration'],self.metadata.calibration)
        self.get_metadata_from_h5_file(h5_file['4DSTEM_experiment']['metadata']['comments'],self.metadata.comments)

    def setup_metadata_hs_file(self, original_metadata_shortlist=None, original_metadata_all=None):
        self.setup_metadata_containers()
        self.setup_metadata_search_dicts()

        # Store original metadata
        self.metadata.original.shortlist = original_metadata_shortlist
        self.metadata.original.all = original_metadata_all

        # Search original metadata and use to populate metadata groups
        self.get_metadata_from_original_metadata(original_metadata_all, self.original_to_microscope_search_dict, self.metadata.microscope)
        self.get_metadata_from_original_metadata(original_metadata_all, self.original_to_sample_search_dict, self.metadata.sample)
        self.get_metadata_from_original_metadata(original_metadata_all, self.original_to_user_search_dict, self.metadata.user)
        self.get_metadata_from_original_metadata(original_metadata_all, self.original_to_calibration_search_dict, self.metadata.calibration)
        self.get_metadata_from_original_metadata(original_metadata_all, self.original_to_comments_search_dict, self.metadata.comments)

        self.get_metadata_from_original_metadata(original_metadata_shortlist, self.original_to_microscope_search_dict, self.metadata.microscope)
        self.get_metadata_from_original_metadata(original_metadata_shortlist, self.original_to_sample_search_dict, self.metadata.sample)
        self.get_metadata_from_original_metadata(original_metadata_shortlist, self.original_to_user_search_dict, self.metadata.user)
        self.get_metadata_from_original_metadata(original_metadata_shortlist, self.original_to_calibration_search_dict, self.metadata.calibration)
        self.get_metadata_from_original_metadata(original_metadata_shortlist, self.original_to_comments_search_dict, self.metadata.comments)

    def setup_metadata_containers(self):
        """
        Creates the containers for metadata.
        """
        self.metadata = MetadataCollection('metadata')
        self.metadata.original = MetadataCollection('original')
        self.metadata.microscope = dict()
        self.metadata.sample = dict()
        self.metadata.user = dict()
        self.metadata.calibration = dict()
        self.metadata.comments = dict()

    def get_original_metadata_from_h5_file(self, h5_metadata_group, datacube_metadata_group):
        if len(h5_metadata_group.attrs)>0:
            datacube_metadata_group.metadata_items = dict()
            self.get_metadata_from_h5_file(h5_metadata_group, datacube_metadata_group.metadata_items)
        for subgroup_key in h5_metadata_group.keys():
            vars(datacube_metadata_group)[subgroup_key] = MetadataCollection(subgroup_key)
            self.get_original_metadata_from_h5_file(h5_metadata_group[subgroup_key], vars(datacube_metadata_group)[subgroup_key])


    def get_metadata_from_h5_file(self, h5_metadata_group, datacube_metadata_dict):
        for attr in h5_metadata_group.attrs:
            datacube_metadata_dict[attr] = h5_metadata_group.attrs[attr]

    @staticmethod
    def get_metadata_from_original_metadata(hs_tree, metadata_search_dict, metadata_dict):
        """
        Finds the relavant metadata in the original_metadata objects and populates the
        corresponding RawDataCube instance attributes.
        Accepts:
            hs_tree -   a hyperspy.misc.utils.DictionaryTreeBrowser object
            metadata_search_dict -  a dictionary with the attributes to search and the keys
                                    under which to find them
            metadata_dict - a dictionary to put the found key:value pairs into
        """
        for attr, keys in metadata_search_dict.items():
            metadata_dict[attr]=""
            for key in keys:
                found, value = RawDataCube.search_hs_tree(key, hs_tree)
                if found:
                    metadata_dict[attr]=value
                    break

    @staticmethod
    def search_hs_tree(key, hs_tree):
        """
        Searchers heirachically through a hyperspy.misc.utils.DictionaryBrowserTree object for
        an attribute named 'key'.
        If found, returns True, Value.
        If not found, returns False, -1.
        """
        if hs_tree is None:
            return False, -1
        else:
            for hs_key in hs_tree.keys():
                if not RawDataCube.istree_hs(hs_tree[hs_key]):
                    if key==hs_key:
                        return True, hs_tree[hs_key]
                else:
                    found, val = RawDataCube.search_hs_tree(key, hs_tree[hs_key])
                    if found:
                        return found, val
            return False, -1

    @staticmethod
    def istree_hs(node):
        if type(node)==DictionaryTreeBrowser:
            return True
        else:
            return False

    def setup_metadata_search_dicts(self):
        """
        Make dictionaties for searching/scraping/populating the active metadata dictionaries
        from the original metadata.
        Keys become the keys in the final, active metadata dictioaries; values are lists
        containing the corresponding keys to find in the hyperspy trees of the original metadata.
        These objects live in the RawDataCube class scope.

        Note that items that are not found will still be stored as a key in the relevant metadata
        dictionary, with the empty string as its value.  This allows these fields to populate
        in the relevant places - i.e. the metadata editor dialog. Thus any desired fields which
        will not be in the original metadata should be entered as keys with an empty seach list.
        """
        self.original_to_microscope_search_dict = {
            'accelerating_voltage' : [ 'beam_energy' ],
            'accelerating_voltage_units' : [ '' ],
            'camera_length' : [ 'camera_length' ],
            'camera_length_units' : [ '' ],
            'C2_aperture' : [ '' ],
            'convergence_semiangle_mrad' : [ '' ],
            'spot_size' : [ '' ],
            'scan_rotation_degrees' : [ '' ],
            'dwell_time' : [ '' ],
            'dwell_time_units' : [ '' ],
            'scan_size_Ny' : [ '' ],
            'scan_size_Nx' : [ '' ],
            'R_pix_size' : [ '' ],
            'R_pix_units' : [ '' ],
            'K_pix_size' : [ '' ],
            'K_pix_units' : [ '' ],
            'probe_FWHM_nm' : [ '' ],
            'acquisition_date' : [ '' ],
            'original_filename' : [ 'original_filename' ],
        }

        self.original_to_sample_search_dict = {
            'sample' : [ '' ],
            'preparation_method' : [ '' ],
            'growth_method' : [ '' ],
            'grown_by' : [ '' ],
            'other_notes' : [ '' ]
        }

        self.original_to_user_search_dict = {
            'name' : [ '' ],
            'institution' : [ '' ],
            'department' : [ '' ],
            'contact_email' : [ '' ],
            'contact_number' : [ '' ]
        }

        self.original_to_calibration_search_dict = {
            'R_pix_size' : [ '' ],
            'R_pix_units' : [ '' ],
            'K_pix_size' : [ '' ],
            'K_pix_units' : [ '' ],
            'R_to_K_rotation_degrees' : [ '' ]
        }

        self.original_to_comments_search_dict = {
            'comments' : [ '' ]
        }

    @staticmethod
    def add_metadata_item(key,value,metadata_dict):
        """
        Adds a single item, given by the pair key:value, to the metadata dictionary metadata_dict
        """
        metadata_dict[key] = value

########################## END OF RAWDATACUBE OBJECT ########################


class MetadataCollection(object):
    """
    Empty container for storing metadata.
    """
    def __init__(self,name):
        self.__name__ = name


### A note on metadata ##
# Metadata exists in 3 different ways in the program.
# (1) At readtime, hyperspy reads in the file and stores metadata in the native hyperspy tree
# structure hyperspy.misc.utils.DictionaryTreeBrowser
# (2) Any metadata that is important to the py4DSTEM will be saved as an attribute in the 
# DataCube object.  The Datacube additionally keeps a copy of the original hyperspy metadata 
# trees
# (3) When saved to a .h5, metadata is copied into a metadata group.  This includes, in separate
# subgroups, both the original hyperspy metadata (in an identical tree structure, written in .h5
# groups/attrs), and the metadata used by py4DSTEM

