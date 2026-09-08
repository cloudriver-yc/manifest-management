package schema

// SystemManifests represents the complete unified configuration state
#SystemManifests: {
	environments: [string]:       #Environment
	application_groups: [string]: #ApplicationGroup
	namespaces: [string]:         #Namespace
	gateways: [string]:           #Gateway
	http_routes: [string]:        #HTTPRoute
	reference_grants?: [string]:  #ReferenceGrant
	services: [string]:           #Service
	service_defaults: [string]:   #ServiceDefaults
	proxy_defaults: [string]:     #ProxyDefaults
	service_resolvers?: [string]: #ServiceResolver
	mesh_services?: [string]:     #MeshService
	network_policies?: [string]:  #NetworkPolicy
}

