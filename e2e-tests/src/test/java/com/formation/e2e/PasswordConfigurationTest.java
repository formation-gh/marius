package com.formation.e2e;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PasswordConfigurationTest {

    @Test
    void unMotDePasseAbsentEstSignale() {
        IllegalStateException exception = assertThrows(IllegalStateException.class,
                () -> FormationGhApiE2ETest.motDePasseObligatoire(null));

        assertEquals("La variable d'environnement E2E_APP_PASSWORD est requise.", exception.getMessage());
    }

    @Test
    void unMotDePasseVideEstSignale() {
        assertThrows(IllegalStateException.class,
                () -> FormationGhApiE2ETest.motDePasseObligatoire("   "));
    }
}
