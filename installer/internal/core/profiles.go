package core

type ProfileInfo struct {
	ID             Profile
	Title, Summary string
}

var ProfileCatalog = []ProfileInfo{
	{ProfileCore, "Core", "Facturación, ventas, remitos, WhatsApp, IA/OCR y tema"},
	{ProfileCommerce, "Comercio", "Core más Punto de Venta"},
	{ProfileServices, "Servicios", "Core más suscripciones, alquileres y BI"},
	{ProfileFull, "Full", "Catálogo DOLAN completo y aplicaciones CE de negocio"},
	{ProfileCustom, "Custom", "Selección de módulos DOLAN disponibles"},
}
