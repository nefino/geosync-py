import sgqlc.types
import sgqlc.types.datetime

schema = sgqlc.types.Schema()


########################################################################
# Scalars and Enumerations
########################################################################
Boolean = sgqlc.types.Boolean


class CRSType(sgqlc.types.Enum):
    __schema__ = schema
    __choices__ = ('EPSG_25832', 'EPSG_25833', 'EPSG_3035', 'EPSG_4326')


class LayerChangeAction(sgqlc.types.Enum):
    __schema__ = schema
    __choices__ = ('created', 'updated', 'deleted', 'regions_changed')


DateTime = sgqlc.types.datetime.DateTime

Float = sgqlc.types.Float

ID = sgqlc.types.ID

Int = sgqlc.types.Int


class OutputObjectType(sgqlc.types.Enum):
    __schema__ = schema
    __choices__ = ('GPKG', 'QGIS_AND_GPKG', 'QGIS_PRJ', 'SHP')


class PlaceTypeGeo(sgqlc.types.Enum):
    __schema__ = schema
    __choices__ = (
        'ADMINISTRATIVE_UNIT_GEO',
        'COUNTRY',
        'FEDERAL_STATE_GEO',
        'LOCAL_ADMINISTRATIVE_UNITS_GEO',
        'PLANNING_REGIONS_GEO',
    )


class PlaceTypeNews(sgqlc.types.Enum):
    __schema__ = schema
    __choices__ = (
        'ADMINISTRATIVE_UNIT',
        'COUNTRY',
        'COUNTY',
        'FEDERAL_STATE',
        'LOCAL_ADMINISTRATIVE_UNITS',
        'PLANNING_REGIONS',
    )


class ScopeType(sgqlc.types.Enum):
    __schema__ = schema
    __choices__ = (
        'ADMINISTRATIVE_UNIT',
        'FEDERAL_STATE',
        'LOCAL_ADMINISTRATIVE_UNIT',
        'PLANNING_REGION',
        'POLYGON',
        'RADIUS',
        'SQUARE',
    )


class Status(sgqlc.types.Enum):
    __schema__ = schema
    __choices__ = ('ERROR', 'PENDING', 'RUNNING', 'SUCCESS')


String = sgqlc.types.String


class UUID(sgqlc.types.Scalar):
    __schema__ = schema


########################################################################
# Input Objects
########################################################################
class CoordinateInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('lon', 'lat')
    lon = sgqlc.types.Field(sgqlc.types.non_null(Float), graphql_name='lon')
    lat = sgqlc.types.Field(sgqlc.types.non_null(Float), graphql_name='lat')


class GeoAnalysisInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('name', 'specs')
    name = sgqlc.types.Field(String, graphql_name='name')
    specs = sgqlc.types.Field(sgqlc.types.non_null('GeoAnalysisObjectInput'), graphql_name='specs')


class GeoAnalysisLayerInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('layer_name', 'buffer_m')
    layer_name = sgqlc.types.Field(sgqlc.types.non_null(String), graphql_name='layerName')
    buffer_m = sgqlc.types.Field(
        sgqlc.types.non_null(sgqlc.types.list_of(sgqlc.types.non_null(Int))),
        graphql_name='bufferM',
    )


class GeoAnalysisObjectInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('coordinate', 'scope', 'requests', 'operations', 'output')
    coordinate = sgqlc.types.Field(sgqlc.types.non_null(CoordinateInput), graphql_name='coordinate')
    scope = sgqlc.types.Field(sgqlc.types.non_null('GeoAnalysisScopeInput'), graphql_name='scope')
    requests = sgqlc.types.Field(
        sgqlc.types.non_null(sgqlc.types.list_of(sgqlc.types.non_null('GeoAnalysisRequestInput'))),
        graphql_name='requests',
    )
    operations = sgqlc.types.Field(
        sgqlc.types.non_null(sgqlc.types.list_of(sgqlc.types.non_null('GeoAnalysisOperationInput'))),
        graphql_name='operations',
    )
    output = sgqlc.types.Field(sgqlc.types.non_null('GeoAnalysisOutputFormatInput'), graphql_name='output')


class GeoAnalysisOperationInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('operation_name', 'input')
    operation_name = sgqlc.types.Field(sgqlc.types.non_null(String), graphql_name='operationName')
    input = sgqlc.types.Field(sgqlc.types.non_null(sgqlc.types.list_of(String)), graphql_name='input')


class GeoAnalysisOutputFormatInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('template_name', 'type', 'crs')
    template_name = sgqlc.types.Field(sgqlc.types.non_null(String), graphql_name='templateName')
    type = sgqlc.types.Field(sgqlc.types.non_null(OutputObjectType), graphql_name='type')
    crs = sgqlc.types.Field(sgqlc.types.non_null(CRSType), graphql_name='crs')


class GeoAnalysisRequestInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('cluster_name', 'layers')
    cluster_name = sgqlc.types.Field(sgqlc.types.non_null(String), graphql_name='clusterName')
    layers = sgqlc.types.Field(
        sgqlc.types.non_null(sgqlc.types.list_of(sgqlc.types.non_null(GeoAnalysisLayerInput))),
        graphql_name='layers',
    )


class GeoAnalysisScopeInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = ('type', 'radius', 'sides', 'polygon', 'place')
    type = sgqlc.types.Field(sgqlc.types.non_null(ScopeType), graphql_name='type')
    radius = sgqlc.types.Field(Float, graphql_name='radius')
    sides = sgqlc.types.Field(Float, graphql_name='sides')
    polygon = sgqlc.types.Field(String, graphql_name='polygon')
    place = sgqlc.types.Field(String, graphql_name='place')


class LayerChangelogInput(sgqlc.types.Input):
    __schema__ = schema
    __field_names__ = (
        'layer_id',
        'cluster_id',
        'layer_name',
        'cluster_name',
        'timestamp_start',
        'timestamp_end',
        'changed_field',
        'action',
    )
    layer_id = sgqlc.types.Field(Int, graphql_name='layerId')
    cluster_id = sgqlc.types.Field(Int, graphql_name='clusterId')
    layer_name = sgqlc.types.Field(String, graphql_name='layerName')
    cluster_name = sgqlc.types.Field(String, graphql_name='clusterName')
    timestamp_start = sgqlc.types.Field(DateTime, graphql_name='timestampStart')
    timestamp_end = sgqlc.types.Field(DateTime, graphql_name='timestampEnd')
    changed_field = sgqlc.types.Field(String, graphql_name='changedField')
    action = sgqlc.types.Field(LayerChangeAction, graphql_name='action')


########################################################################
# Output Objects and Interfaces
########################################################################
class MinimalAnalysis(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = ('started_at', 'pk', 'status', 'url')
    started_at = sgqlc.types.Field(DateTime, graphql_name='startedAt')
    pk = sgqlc.types.Field(sgqlc.types.non_null(ID), graphql_name='pk')
    status = sgqlc.types.Field(sgqlc.types.non_null(Status), graphql_name='status')
    url = sgqlc.types.Field(String, graphql_name='url')


class MinimalAreasEnabled(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = ('all_areas_enabled', 'enabled_states')
    all_areas_enabled = sgqlc.types.Field(sgqlc.types.non_null(Boolean), graphql_name='allAreasEnabled')
    enabled_states = sgqlc.types.Field(sgqlc.types.list_of('PlaceIdentifier'), graphql_name='enabledStates')


class MinimalCluster(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = ('name', 'layers', 'has_access')
    name = sgqlc.types.Field(sgqlc.types.non_null(String), graphql_name='name')
    layers = sgqlc.types.Field(
        sgqlc.types.non_null(sgqlc.types.list_of(sgqlc.types.non_null('MinimalLayer'))),
        graphql_name='layers',
    )
    has_access = sgqlc.types.Field(Boolean, graphql_name='hasAccess')


class MinimalGeoAccessRule(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = ('all_clusters_enabled', 'clusters', 'places')
    all_clusters_enabled = sgqlc.types.Field(sgqlc.types.non_null(Boolean), graphql_name='allClustersEnabled')
    clusters = sgqlc.types.Field(sgqlc.types.list_of(String), graphql_name='clusters')
    places = sgqlc.types.Field(sgqlc.types.list_of(String), graphql_name='places')


class MinimalLayer(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = ('name', 'pre_buffer', 'last_update', 'is_regional')
    name = sgqlc.types.Field(sgqlc.types.non_null(String), graphql_name='name')
    pre_buffer = sgqlc.types.Field(sgqlc.types.non_null(Int), graphql_name='preBuffer')
    last_update = sgqlc.types.Field(DateTime, graphql_name='lastUpdate')
    is_regional = sgqlc.types.Field(sgqlc.types.non_null(Boolean), graphql_name='isRegional')


class LayerChangelogEntry(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = (
        'layer_name',
        'timestamp',
        'action',
        'changed_fields',
        'attributes',
        'layer_id',
        'last_update',
        'cluster_name',
        'cluster_id',
    )
    layer_name = sgqlc.types.Field(String, graphql_name='layerName')
    timestamp = sgqlc.types.Field(DateTime, graphql_name='timestamp')
    action = sgqlc.types.Field(LayerChangeAction, graphql_name='action')
    changed_fields = sgqlc.types.Field(sgqlc.types.list_of(String), graphql_name='changedFields')
    attributes = sgqlc.types.Field(sgqlc.types.list_of(String), graphql_name='attributes')
    layer_id = sgqlc.types.Field(Int, graphql_name='layerId')
    last_update = sgqlc.types.Field(DateTime, graphql_name='lastUpdate')
    cluster_name = sgqlc.types.Field(String, graphql_name='clusterName')
    cluster_id = sgqlc.types.Field(Int, graphql_name='clusterId')


class Mutation(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = ('start_analysis',)
    start_analysis = sgqlc.types.Field(
        MinimalAnalysis,
        graphql_name='startAnalysis',
        args=sgqlc.types.ArgDict(
            (
                (
                    'inputs',
                    sgqlc.types.Arg(
                        sgqlc.types.non_null(GeoAnalysisInput),
                        graphql_name='inputs',
                        default=None,
                    ),
                ),
            )
        ),
    )


class PlaceIdentifier(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = ('place_id', 'place_type')
    place_id = sgqlc.types.Field(sgqlc.types.non_null(ID), graphql_name='placeId')
    place_type = sgqlc.types.Field(sgqlc.types.non_null(PlaceTypeNews), graphql_name='placeType')


class Query(sgqlc.types.Type):
    __schema__ = schema
    __field_names__ = (
        'analysis_metadata',
        'allowed_analysis_areas',
        'clusters',
        'regional_layers',
        'access_rules',
        'layer_changelog',
    )
    analysis_metadata = sgqlc.types.Field(
        sgqlc.types.list_of(MinimalAnalysis),
        graphql_name='analysisMetadata',
        args=sgqlc.types.ArgDict(
            (
                (
                    'analysis_id',
                    sgqlc.types.Arg(UUID, graphql_name='analysisId', default=None),
                ),
            )
        ),
    )
    allowed_analysis_areas = sgqlc.types.Field(MinimalAreasEnabled, graphql_name='allowedAnalysisAreas')
    clusters = sgqlc.types.Field(sgqlc.types.list_of(MinimalCluster), graphql_name='clusters')
    regional_layers = sgqlc.types.Field(
        sgqlc.types.list_of(MinimalLayer),
        graphql_name='regionalLayers',
        args=sgqlc.types.ArgDict(
            (
                (
                    'place_type',
                    sgqlc.types.Arg(
                        sgqlc.types.non_null(PlaceTypeGeo),
                        graphql_name='placeType',
                        default=None,
                    ),
                ),
                (
                    'place_id',
                    sgqlc.types.Arg(
                        sgqlc.types.non_null(String),
                        graphql_name='placeId',
                        default=None,
                    ),
                ),
            )
        ),
    )
    access_rules = sgqlc.types.Field(sgqlc.types.list_of(MinimalGeoAccessRule), graphql_name='accessRules')
    layer_changelog = sgqlc.types.Field(
        sgqlc.types.list_of(LayerChangelogEntry),
        graphql_name='layerChangelog',
        args=sgqlc.types.ArgDict(
            (
                (
                    'inputs',
                    sgqlc.types.Arg(LayerChangelogInput, graphql_name='inputs', default=None),
                ),
            )
        ),
    )


########################################################################
# Unions
########################################################################

########################################################################
# Schema Entry Points
########################################################################
schema.query_type = Query
schema.mutation_type = Mutation
schema.subscription_type = None
