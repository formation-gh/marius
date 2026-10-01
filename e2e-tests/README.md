# Tests end to end — formation-gh-api

Ce module contient un test end to end (E2E) écrit en Java qui vérifie que
l'application déployée sur GitHub Pages à l'adresse
[https://aouzgaga.github.io/formation-gh-api/](https://aouzgaga.github.io/formation-gh-api/)
se charge correctement et ne renvoie aucune erreur.

## Scénarios testés

- la page d'accueil affiche bien les 3 utilisateurs de départ ;
- la page d'un utilisateur affiche son solde, permet de poser un congé,
  conserve les données après rechargement puis permet de supprimer le congé ;
- une période ne contenant aucun jour ouvré est refusée ;
- une période qui chevauche un congé existant affiche une erreur ;
- une période trop longue désactive le bouton de validation ;
- une route inconnue affiche la page introuvable.

## Technologies utilisées

- Java 17
- Maven
- [Selenium WebDriver](https://www.selenium.dev/) pour piloter le navigateur
- [WebDriverManager](https://github.com/bonigarcia/webdrivermanager) pour
  gérer automatiquement le driver Chrome (`chromedriver`)
- JUnit 5

## Prérequis

- Java 17+
- Maven 3.6+
- Google Chrome (ou Chromium) installé sur la machine

Si un `chromedriver` est déjà installé sur la machine (par exemple dans
`/usr/bin/chromedriver`), il est automatiquement réutilisé. Sinon,
WebDriverManager télécharge la version compatible avec le Chrome installé
(nécessite un accès réseau à `googlechromelabs.github.io`). Il est également
possible de forcer l'emplacement du driver via la variable d'environnement
`WEBDRIVER_CHROME_DRIVER`.

## Exécuter les tests

```bash
cd e2e-tests
mvn test
```
