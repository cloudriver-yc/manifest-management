package extensions

import (
	"manifest.management/schema"
)

ext_environments: [string]: schema.#Environment
ext_environments: {}

ext_application_groups: [string]: schema.#ApplicationGroup
ext_application_groups: {}

ext_namespaces: [string]: schema.#Namespace
ext_namespaces: {}

ext_gateways: [string]: schema.#Gateway
ext_gateways: {}

ext_http_routes: [string]: schema.#HTTPRoute
ext_http_routes: {}

ext_services: [string]: schema.#Service
ext_services: {}

ext_service_defaults: [string]: schema.#ServiceDefaults
ext_service_defaults: {}

ext_proxy_defaults: [string]: schema.#ProxyDefaults
ext_proxy_defaults: {}

ext_reference_grants: [string]: schema.#ReferenceGrant
ext_reference_grants: {}

ext_service_resolvers: [string]: schema.#ServiceResolver
ext_service_resolvers: {}

ext_mesh_services: [string]: schema.#MeshService
ext_mesh_services: {}

ext_network_policies: [string]: schema.#NetworkPolicy
ext_network_policies: {}
