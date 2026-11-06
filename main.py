
def display_menu():
    print("Bienvenido a Time Tracker\n")
    print("1. Cargar sesión de trabajo")
    print("2. Nueva sesión de trabajo")
    print("3. Lista de sesiones de trabajo")
    print("4. Eliminar sesión de trabajo")
    print("5. Salir")

def main():
    # Your main code logic here
    while True:
        display_menu()
        choice = input("Ingrese su elección (1-5): ")
        
        if choice == '1':
            print("Cargando sesión de trabajo...")
            # Logic to load work session
        elif choice == '2':
            print("Iniciando nueva sesión de trabajo...")
            # Logic to start new work session
        elif choice == '3':
            print("Mostrando lista de sesiones de trabajo...")
            # Logic to list work sessions
        elif choice == '4':
            print("Eliminando sesión de trabajo...")
            # Logic to delete work session
        elif choice == '5':
            print("Saliendo del programa. ¡Hasta luego!")
            break
        else:
            print("Opción inválida. Por favor, elige una opción válida.")

if __name__== "__main__":
    # Your main code logic here
    main()