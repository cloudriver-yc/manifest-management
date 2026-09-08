package catalog

import (
	"manifest.management/schema"
	"manifest.management/catalog/apgs"
	"manifest.management/catalog/environments"
	"manifest.management/catalog/extensions"
)

system: schema.#SystemManifests & {
	"environments":       environments.environments & extensions.ext_environments
	"application_groups": apgs.application_groups & extensions.ext_application_groups
	"namespaces":         apgs.namespaces & extensions.ext_namespaces
	"gateways":           apgs.gateways & extensions.ext_gateways
	"http_routes":        apgs.http_routes & extensions.ext_http_routes
	"services":           apgs.services & extensions.ext_services
	"service_defaults":   apgs.service_defaults & extensions.ext_service_defaults
	"proxy_defaults":     environments.proxy_defaults_list & extensions.ext_proxy_defaults
	"reference_grants":   extensions.ext_reference_grants
	"service_resolvers":  extensions.ext_service_resolvers
	"mesh_services":      extensions.ext_mesh_services
	"network_policies":   extensions.ext_network_policies
}
