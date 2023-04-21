# Defines the BraggVectors class

from typing import Optional,Union
import numpy as np
from os.path import basename

from py4DSTEM.classes import Data
from py4DSTEM.process.diskdetection.braggvector_methods import BraggVectorMethods
from emdfile import Custom,PointListArray,PointList,Metadata



class BraggVectors(Custom,BraggVectorMethods,Data):
    """
    Stores localized bragg scattering positions and intensities
    for a 4D-STEM datacube.

    Raw (detector coordinate) vectors are accessible as

        >>> braggvectors.raw[ scan_x, scan_y ]

    and calibrated vectors as

        >>> braggvectors.cal[ scan_x, scan_y ]

    To set which calibrations are being applied, call

        >>> braggvectors.setcal(
        >>>     center = bool,
        >>>     ellipse = bool,
        >>>     pixel = bool,
        >>>     rot = bool
        >>> )

    If .setcal is not called, calibrations will be automatically selected based
    based on the contents of the instance's `calibrations` property. The
    calibrations performed in the last call to `braggvectors.cal` are exposed as

        >>> braggvectors.calstate

    After grabbing some vectors

        >>> vects = braggvectors.raw[ scan_x,scan_y ]

    the values themselves are accessible as

        >>> vects.qx,vects.qy,vects.I
        >>> vects['qx'],vects['qy'],vects['intensity']

    """

    def __init__(
        self,
        Rshape,
        Qshape,
        name = 'braggvectors'
        ):
        Custom.__init__(self,name=name)

        self.Rshape = Rshape
        self.shape = self.Rshape
        self.Qshape = Qshape

        self._v_uncal = PointListArray(
            dtype = [
                ('qx',np.float64),
                ('qy',np.float64),
                ('intensity',np.float64)
            ],
            shape = Rshape,
            name = '_v_uncal'
        )

        # initial calibration state
        self._calstate = None
        self._raw_vector_getter = None
        self._cal_vector_getter = None

    @property
    def calstate(self):
        return self._calstate



    # raw vectors

    @property
    def raw(self):
        """
        Calling

            >>> raw[ scan_x, scan_y ]

        returns those bragg vectors.
        """

        # check if a raw vector getter exists
        # if it doesn't, make it
        if self._raw_vector_getter is None:
            self._raw_vector_getter = RawVectorGetter(
                data = self._v_uncal
            )

        # use the vector getter to grab the vector
        return self._raw_vector_getter



    # calibrated vectors

    @property
    def cal(self):
        """
        Calling

            >>> cal[ scan_x, scan_y ]

        retrieves data.  Use `.setcal` to set the calibrations to be applied, or
        `.calstate` to see which calibrations are currently set.  Requesting data
        before setting calibrations will automatically select values based
        calibrations that are available.
        """

        # check if a calibration state is set
        # if not, autoselect calibrations and make a getter
        if self.calstate is None:
            self.setcal()

        # retrieve the getter and return
        return self._cal_vector_getter


    # set calibration state

    def setcal(
        self,
        center = None,
        ellipse = None,
        pixel = None,
        rot = None,
    ):
        """
        Calling

            >>> braggvectors.setcal(
            >>>     center = bool,
            >>>     ellipse = bool,
            >>>     pixel = bool,
            >>>     rot = bool,
            >>> )

        sets the calibrations that will be applied to vectors subsequently
        retrieved with

            >>> braggvectors.cal[ scan_x, scan_y ]

        Any arguments left as `None` will be automatically set based on
        the calibration measurements available.
        """

        # autodetect
        c = self.calibration
        if center is None:
            center = False if c.get_origin() is None else True
        if ellipse is None:
            ellipse = False if c.get_ellipse() is None else True
        if pixel is None:
            pixel = False if c.get_Q_pixel_size() != 1 else True
        if rot is None:
            rot = False if c.get_QR_rotflip() is None else True

        # validate requested state
        if center:
            assert(c.get_origin() is not None), "Requested calibrations not found"
        if ellipse:
            assert(c.get_ellipse() is not None), "Requested calibrations not found"
        if pixel:
            assert(c.get_Q_pixel_size() is not None), "Requested calibrations not found"
        if rot:
            assert(c.get_RQ_rotflip() is not None), "Requested calibrations not found"

        # make the requested vector getter
        self._calstate = {
            "center" : center,
            "ellipse" : ellipse,
            "pixel" : pixel,
            "rot" : rot,
        }
        self._cal_vector_getter = CalibratedVectorGetter( braggvects = self )

        pass



    # copy

    def copy(self, name=None):
        name = name if name is not None else self.name+"_copy"
        braggvector_copy = BraggVectors(self.Rshape, self.Qshape, name=name)
        braggvector_copy._v_uncal = self._v_uncal.copy()
        try:
            braggvector_copy._v_cal = self._v_cal.copy()
        except AttributeError:
            pass
        for k in self.metadata.keys():
            braggvector_copy.metadata = self.metadata[k].copy()
        self.root.tree(braggvector_copy)

        return braggvector_copy


    # write

    def to_h5(self,group):
        """ Constructs the group, adds the bragg vector pointlists,
        and adds metadata describing the shape
        """
        md = Metadata( name = '_braggvectors_shape' )
        md['Rshape'] = self.Rshape
        md['Qshape'] = self.Qshape
        self.metadata = md
        grp = Custom.to_h5(self,group)


    # read

    @classmethod
    def _get_constructor_args(cls,group):
        """
        """
        # Get shape metadata from the metadatabundle group
        assert('metadatabundle' in group.keys()), "No metadata found, can't get Rshape and Qshape"
        grp_metadata = group['metadatabundle']
        assert('_braggvectors_shape' in grp_metadata.keys()), "No _braggvectors_shape metadata found"
        md = Metadata.from_h5(grp_metadata['_braggvectors_shape'])
        # Populate args and return
        kwargs = {
            'name' : basename(group.name),
            'Rshape' : md['Rshape'],
            'Qshape' : md['Qshape']
        }
        return kwargs

    def _populate_instance(self,group):
        """
        """
        dic = self._get_emd_attr_data(group)
        assert('_v_uncal' in dic.keys()), "Uncalibrated bragg vectors not found!"
        self._v_uncal = dic['_v_uncal']
        if '_v_cal' in dic.keys():
            self._v_cal = dic['_v_cal']


    # standard output display

    def __repr__(self):

        space = ' '*len(self.__class__.__name__)+'  '
        string = f"{self.__class__.__name__}( "
        string += f"A {self.shape}-shaped array of lists of bragg vectors )"
        return string





# Vector access classes


class BVects:
    """
    Enables

        >>> v.qx,v.qy,v.I

    -like access to a collection of Bragg vector.
    """

    def __init__(
        self,
        data
        ):
        """ pointlist must have fields 'qx', 'qy', and 'intensity'
        """
        self._data = data

    @property
    def qx(self):
        return self._data['qx']
    @property
    def qy(self):
        return self._data['qy']
    @property
    def I(self):
        return self._data['intensity']


class RawVectorGetter:
    def __init__(
        self,
        data
    ):
        self._data = data

    def __getitem__(self,pos):
        x,y = pos
        ans = self._data[x,y].data
        return BVects(ans)


class CalibratedVectorGetter:

    def __init__(
        self,
        braggvects,
    ):
        self._bvects = braggvects
        self._data = braggvects._v_uncal
        self.calstate = braggvects.calstate

    def __getitem__(self,pos):
        x,y = pos
        ans = self._data[x,y].data
        ans = self._transform(
            data = ans,
            cal = self._bvects.calibration,
            scanxy = (x,y),
            center = self.calstate['center'],
            ellipse = self.calstate['ellipse'],
            pixel = self.calstate['pixel'],
            rot = self.calstate['rot'],
        )
        return BVects(ans)

    def _transform(
        self,
        data,
        cal,
        scanxy,
        center,
        ellipse,
        pixel,
        rot,
        ):
        """
        Return a transformed copy of stractured data `data` with fields
        with fields 'qx','qy','intensity', applying calibrating transforms
        according to the values of center, ellipse, pixel, using the
        measurements found in Calibration instance cal for scan position scanxy.
        """

        ans = data.copy()
        x,y = scanxy

        # origin

        if center:
            origin = cal.get_origin(x,y)
            ans['qx'] -= origin[0]
            ans['qy'] -= origin[1]


        # ellipse
        if ellipse:
            a,b,theta = cal.get_ellipse(x,y)
            # Get the transformation matrix
            e = b/a
            sint, cost = np.sin(theta-np.pi/2.), np.cos(theta-np.pi/2.)
            T = np.array(
                    [
                        [e*sint**2 + cost**2, sint*cost*(1-e)],
                        [sint*cost*(1-e), sint**2 + e*cost**2]
                    ]
                )
            # apply it
            xyar_i = np.vstack([ans['qx'],ans['qy']])
            xyar_f = np.matmul(T, xyar_i)
            ans['qx'] = xyar_f[0, :]
            ans['qy'] = xyar_f[1, :]


        # pixel size
        if pixel:
            qpix = cal.get_Q_pixel_size()
            ans['qx'] *= qpix
            ans['qy'] *= qpix


        # Q/R rotation
        if rot:
            flip = cal.get_QR_flip()
            theta = cal.get_QR_rotation_degrees()
            # rotation matrix
            R = np.array([
                [np.cos(theta), -np.sin(theta)],
                [np.sin(theta), np.cos(theta)]])
            # apply
            if flip:
                positions = R @ np.vstack((ans["qy"], ans["qx"]))
            else:
                positions = R @ np.vstack((ans["qx"], ans["qy"]))
            # update
            ans['qx'] = positions[0,:]
            ans['qy'] = positions[1,:]


        # return
        return ans



