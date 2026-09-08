package schema

// Gateway (AGW) representation
#Gateway: {
	name:      string
	apg:       string
	cell:      string
	region:    #Region
	env?:      string
	cluster?:  string
	namespace: string
	listeners: [...{
		name:      string
		port:      int | *8080
		protocol:  string | *"HTTP"
		hostname?: string
	}]
}

// Destination backend reference in an HTTPRoute
#HTTPRouteBackendRef: {
	service:   string
	port:      int | *8080
	namespace: string
	weight:    int | *100
}

// Match rule for paths and headers
#HTTPRouteMatch: {
	path: {
		type:  "PathPrefix" | "Exact" | *"PathPrefix"
		value: string
	}
	headers?: [string]: string
}

// HTTPRoute Rule containing matches and backends
#HTTPRouteRule: {
	name?:        string
	matches:      [...#HTTPRouteMatch]
	backendRefs:  [...#HTTPRouteBackendRef]
}

// HTTPRoute bounded to a parent AGW
#HTTPRoute: {
	name:       string
	namespace:  string
	apg:        string
	cell:       string
	region:     #Region
	env?:       string
	cluster?:   string
	parent_agw: string
	rules:      [...#HTTPRouteRule]
}


// ReferenceGrant definition in Gateway API
#ReferenceGrantFrom: {
	group:     string | *"gateway.networking.k8s.io"
	kind:      string | *"HTTPRoute"
	namespace: string
}

#ReferenceGrantTo: {
	group: string | *""
	kind:  string | *"Service"
	name?: string
}

#ReferenceGrant: {
	name:      string
	namespace: string
	apg:       string
	cell:      string
	region:    #Region
	env?:      string
	cluster?:  string
	from:      [...#ReferenceGrantFrom]
	to:        [...#ReferenceGrantTo]
}

// NetworkPolicy representation
#NetworkPolicy: {
	name:         string
	namespace:    string
	apg:          string
	cell:         string
	region?:      #Region
	env?:         string
	cluster?:     string
	podSelector?: [string]: string
	policyTypes?: [...string]
}

